from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
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

    @app.post("/api/books")
    async def register_book(
        title: str | None = Form(None),
        file_path: str | None = Form(None),
        file: UploadFile | None = File(None),
    ):
        if file is not None:
            upload_dir = config.data_dir / "uploads"
            upload_dir.mkdir(parents=True, exist_ok=True)
            target_path = upload_dir / file.filename
            target_path.write_bytes(await file.read())
            book_id = Path(file.filename).stem.replace(" ", "-").lower()
            manifest = service.repo.ensure_book_manifest(book_id, title or file.filename, str(target_path))
            return manifest
        chosen_path = Path(file_path) if file_path else config.default_book_path
        if not chosen_path.exists():
            raise HTTPException(status_code=404, detail="book file not found")
        book_id = chosen_path.stem.replace(" ", "-").replace("(", "").replace(")", "").lower()
        manifest = service.repo.ensure_book_manifest(book_id, title or chosen_path.stem, str(chosen_path))
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

    @app.get("/api/dashboard")
    async def get_dashboard():
        return service.get_dashboard_data().model_dump()

    return app


app = create_app()

