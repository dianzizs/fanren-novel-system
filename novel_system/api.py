from __future__ import annotations

import re
import unicodedata
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile


def _fix_filename_encoding(filename: str) -> str:
    """修复 Windows curl 上传时的文件名编码问题（GBK bytes 被当成 UTF-8 解码产生的乱码）"""
    # 检测乱码模式：字符串主要由 Latin-1 补充区字符组成（GBK 字节被 UTF-8 解码的典型特征）
    latin1_like = sum(1 for c in filename if "\u0080" <= c <= "\u00ff") / max(len(filename), 1)
    if latin1_like > 0.3:
        # 将 UTF-8 解码后的"假 Latin-1"字节重新解释为 GBK 编码
        try:
            raw_bytes = filename.encode("utf-8")
            corrected = raw_bytes.decode("gbk", errors="replace")
            if any("\u4e00" <= c <= "\u9fff" for c in corrected):
                return corrected
        except Exception:
            pass
    return filename


def _sanitize_book_id(name: str) -> str:
    """生成安全且可读的书名 ID（不含括号等 URL 不安全字符）"""
    has_cjk = any("\u4e00" <= c <= "\u9fff" for c in name)
    if has_cjk:
        # 保留中文、字母、数字、下划线和连字符，括号替换为连字符
        cleaned = "".join(c if ("\u4e00" <= c <= "\u9fff" or c.isalnum() or c in "_-") else "-" for c in name)
        cleaned = re.sub(r"-+", "-", cleaned).strip(" -")
        return cleaned[:60] if cleaned else name[:30]
    cleaned = "".join(c if c.isalnum() or c in "_-" else "-" for c in name)
    cleaned = re.sub(r"-+", "-", cleaned).strip(" -")
    return cleaned[:60] if cleaned else name[:30]
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from .config import AppConfig
from .models import AskRequest, CanonUpdateRequest, ContinueRequest, Scope
from .service import NovelSystemService, create_service


def create_app() -> FastAPI:
    config = AppConfig.load()
    service = create_service()
    app = FastAPI(title="Novel System Workspace", version="1.0.0")
    app.state.config = config
    app.state.service = service
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.mount("/static", StaticFiles(directory=str(config.root_dir / "static")), name="static")
    templates = Jinja2Templates(directory=str(config.root_dir / "templates"))

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(
            request,
            "dashboard.html",
            {
                "default_book_id": config.default_book_id,
                "default_book_title": config.default_book_title,
            },
        )

    @app.get("/api/books")
    async def list_books():
        return [book.model_dump() for book in service.list_books()]

    @app.get("/api/storage-stats")
    async def get_storage_stats():
        return service.get_storage_stats()

    @app.get("/api/token-stats")
    async def get_token_stats():
        return service.get_token_stats()

    @app.delete("/api/books/{book_id}")
    async def delete_book(book_id: str):
        try:
            return service.delete_book(book_id)
        except FileNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))

    @app.post("/api/books")
    async def register_book(
        title: str | None = Form(None),
        file_path: str | None = Form(None),
        file: UploadFile | None = File(None),
    ):
        if file is not None:
            upload_dir = config.data_dir / "uploads"
            upload_dir.mkdir(parents=True, exist_ok=True)
            raw_filename = file.filename
            fixed_filename = _fix_filename_encoding(raw_filename)
            safe_id = _sanitize_book_id(fixed_filename)
            existing = next((book for book in service.repo.list_books() if book["id"] == safe_id), None)
            if existing and existing.get("status") == "indexing":
                raise HTTPException(status_code=409, detail="book is indexing")
            target_path = upload_dir / fixed_filename
            target_path.write_bytes(await file.read())
            manifest = service.repo.ensure_book_manifest(
                safe_id,
                title or fixed_filename,
                str(target_path),
                source="upload",
                status="pending",
                reset_existing=bool(existing),
            )
            return manifest
        chosen_path = Path(file_path) if file_path else config.default_book_path
        if not chosen_path.exists():
            raise HTTPException(status_code=404, detail="book file not found")
        book_id = chosen_path.stem.replace(" ", "-").replace("(", "").replace(")", "").lower()
        existing = next((book for book in service.repo.list_books() if book["id"] == book_id), None)
        if existing and existing.get("status") == "indexing":
            raise HTTPException(status_code=409, detail="book is indexing")
        manifest = service.repo.ensure_book_manifest(
            book_id,
            title or chosen_path.stem,
            str(chosen_path),
            source="local",
            status="pending",
            reset_existing=bool(existing),
        )
        return manifest

    @app.post("/api/books/{book_id}/index")
    async def index_book(book_id: str):
        books = {book.id: book for book in service.list_books()}
        book = books.get(book_id)
        if book_id == config.default_book_id:
            manifest = service.index_default_book()
            return manifest
        if not book:
            raise HTTPException(status_code=404, detail="book not registered")
        manifest = service.index_book(book_id, book.title, Path(book.source_path))
        return manifest

    @app.get("/api/books/{book_id}/status")
    async def get_book_status(book_id: str):
        try:
            return service.get_book_status(book_id)
        except FileNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))

    @app.post("/api/books/{book_id}/start-index")
    async def start_book_index(book_id: str):
        try:
            return service.start_book_index(book_id)
        except FileNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))

    @app.get("/api/books/{book_id}/artifacts")
    async def get_book_artifacts(book_id: str):
        try:
            return service.get_book_artifact_catalog(book_id)
        except FileNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))

    @app.get("/api/books/{book_id}/artifacts/{artifact_name}")
    async def get_book_artifact(book_id: str, artifact_name: str, full: bool = False, limit: int = 20):
        try:
            return service.get_book_artifact(book_id, artifact_name, full=full, limit=limit)
        except FileNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))

    @app.get("/api/books/{book_id}/reader")
    async def reader_view(book_id: str, chapter: int | None = None):
        return service.get_reader_payload(book_id, chapter)

    @app.post("/api/books/{book_id}/ask")
    async def ask(book_id: str, payload: AskRequest):
        return service.ask(book_id, payload).model_dump()

    @app.post("/api/books/{book_id}/continue")
    async def continue_story(book_id: str, payload: ContinueRequest):
        return service.continue_story(book_id, payload).model_dump()

    @app.get("/api/books/{book_id}/canon")
    async def get_canon(book_id: str, chapter_start: int | None = None, chapter_end: int | None = None):
        scope = Scope(chapters=[chapter_start, chapter_end]) if chapter_start and chapter_end else Scope()
        return service.get_canon(book_id, scope)

    @app.put("/api/books/{book_id}/canon")
    async def update_canon(book_id: str, payload: CanonUpdateRequest):
        return service.update_canon(book_id, payload)

    @app.get("/api/books/{book_id}/timeline")
    async def get_timeline(book_id: str, chapter_start: int | None = None, chapter_end: int | None = None):
        scope = Scope(chapters=[chapter_start, chapter_end]) if chapter_start and chapter_end else Scope()
        return [item.model_dump() for item in service.get_timeline(book_id, scope)]

    @app.get("/api/books/{book_id}/graph")
    async def get_graph(
        book_id: str,
        chapter_start: int | None = None,
        chapter_end: int | None = None,
        center: str | None = None,
        limit: int = 18,
    ):
        scope = Scope(chapters=[chapter_start, chapter_end]) if chapter_start and chapter_end else Scope()
        return service.get_interactive_graph(book_id, scope, center=center, limit=limit)

    @app.get("/api/dashboard")
    async def get_dashboard():
        return service.get_dashboard_data().model_dump()

    return app


app = create_app()
