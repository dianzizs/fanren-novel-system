from __future__ import annotations

import json
import logging
import re
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from ..graphrag_app.paths import graphrag_root
from ..models import BookInfo

logger = logging.getLogger(__name__)


class IndexingServiceMixin:
    """Mixin for book indexing operations, now backed by GraphRAG."""

    def list_books(self) -> list[BookInfo]:
        books = []
        for manifest in self.repo.list_books():
            indexed_at = manifest.get("indexed_at")
            books.append(
                BookInfo(
                    id=manifest["id"],
                    title=manifest["title"],
                    source_path=manifest["source_path"],
                    chapter_count=manifest.get("chapter_count", 0),
                    chunk_count=manifest.get("chunk_count", 0),
                    indexed=manifest.get("indexed", False),
                    indexed_at=datetime.fromisoformat(indexed_at) if indexed_at else None,
                    source=manifest.get("source", "local"),
                    status=manifest.get("status", "pending"),
                    index_progress=manifest.get("index_progress", 0.0),
                    text_unit_count=manifest.get("text_unit_count", 0),
                    entity_count=manifest.get("entity_count", 0),
                    relationship_count=manifest.get("relationship_count", 0),
                    community_count=manifest.get("community_count", 0),
                )
            )
        return books

    def get_book_status(self, book_id: str) -> dict[str, Any]:
        """获取书籍索引状态"""
        manifest = next((book for book in self.repo.list_books() if book["id"] == book_id), None)
        if not manifest:
            raise FileNotFoundError(f"Book {book_id} not found")
        progress = manifest.get("index_progress", 0.0)
        message = self._get_status_message(manifest)
        if manifest.get("status") == "indexing":
            live_status = self._get_live_graphrag_status(book_id, progress)
            if live_status:
                progress = live_status["progress"]
                message = live_status["message"]
        return {
            "book_id": book_id,
            "status": manifest.get("status", "pending"),
            "progress": progress,
            "message": message,
        }

    def _get_status_message(self, manifest: dict[str, Any]) -> str:
        """获取状态描述"""
        status = manifest.get("status", "pending")
        if status == "pending":
            return "等待开始分析"
        elif status == "indexing":
            progress = manifest.get("index_progress", 0)
            return f"正在分析... ({int(progress * 100)}%)"
        elif status == "ready":
            return "分析完成"
        elif status == "error":
            return "分析失败"
        return "未知状态"

    def _get_live_graphrag_status(self, book_id: str, current_progress: float) -> dict[str, Any] | None:
        log_path = graphrag_root(self.config, book_id) / "logs" / "indexing-engine.log"
        if not log_path.exists():
            return None

        try:
            lines = log_path.read_text(encoding="utf-8", errors="ignore").splitlines()[-200:]
        except OSError:
            return None

        patterns = [
            (
                re.compile(r"extract graph progress:\s*(\d+)/(\d+)", re.IGNORECASE),
                0.30,
                0.50,
                "正在抽取实体关系",
            ),
            (
                re.compile(r"Summarize entity/relationship description progress:\s*(\d+)/(\d+)", re.IGNORECASE),
                0.50,
                0.62,
                "正在汇总实体关系描述",
            ),
            (
                re.compile(r"extract claims progress:\s*(\d+)/(\d+)", re.IGNORECASE),
                0.62,
                0.70,
                "正在抽取事件线索",
            ),
            (
                re.compile(r"community reports progress:\s*(\d+)/(\d+)", re.IGNORECASE),
                0.76,
                0.82,
                "正在生成社区报告",
            ),
            (
                re.compile(r"generate text embeddings progress:\s*(\d+)/(\d+)", re.IGNORECASE),
                0.82,
                0.85,
                "正在生成文本向量",
            ),
        ]

        live_status: dict[str, Any] | None = None
        for line in lines:
            for pattern, start, end, label in patterns:
                match = pattern.search(line)
                if not match:
                    continue
                done = int(match.group(1))
                total = max(int(match.group(2)), 1)
                ratio = min(max(done / total, 0.0), 1.0)
                progress = max(current_progress, start + (end - start) * ratio)
                live_status = {
                    "progress": round(progress, 4),
                    "message": f"{label}... ({done}/{total})",
                }

        return live_status

    def set_book_indexing(self, book_id: str, status: str, progress: float = 0.0) -> None:
        """更新书籍索引状态"""
        manifest = next((book for book in self.repo.list_books() if book["id"] == book_id), None)
        if not manifest:
            return
        manifest["status"] = status
        manifest["index_progress"] = progress
        if status == "ready":
            manifest["indexed"] = True
            manifest["indexed_at"] = datetime.now().isoformat()
        self.repo.update_book_manifest(book_id, manifest)

    def start_book_index(self, book_id: str, force: bool = False) -> dict[str, Any]:
        """异步启动书籍索引构建。

        在后台线程中执行索引构建，包括章节解析、切片、向量化等步骤。
        可通过 get_book_status() 查询进度。

        Args:
            book_id: 书籍 ID
            force: 是否强制重建索引，如果为 True，则跳过 "ready" 状态的检查

        Returns:
            包含 status 和 message 的状态字典
        """
        manifest = next((book for book in self.repo.list_books() if book["id"] == book_id), None)
        if not manifest:
            raise FileNotFoundError(f"Book {book_id} not found")

        if manifest.get("status") == "indexing":
            return {"status": "indexing", "message": "正在分析中"}

        if manifest.get("status") == "ready" and not force:
            return {"status": "ready", "message": "已经分析完成"}

        self.set_book_indexing(book_id, "indexing", 0.0)

        thread = threading.Thread(
            target=self._run_book_index,
            args=(book_id,),
            daemon=True,
        )
        thread.start()
        return {"status": "indexing", "message": "开始分析"}

    def _run_book_index(self, book_id: str) -> None:
        """GraphRAG indexing pipeline.

        1. Prepare workspace
        2. Build input text files
        3. Generate settings.yaml
        4. Run GraphRAG CLI index
        5. Validate output tables
        6. Build derived views
        """
        try:
            self.set_book_indexing(book_id, "indexing", 0.02)
            manifest = next((b for b in self.repo.list_books() if b["id"] == book_id), None)
            if not manifest:
                return
            source_path = Path(manifest["source_path"])
            title = manifest.get("title", book_id)

            self.graphrag_workspace.prepare(book_id, source_path)
            self.set_book_indexing(book_id, "indexing", 0.10)

            self.graphrag_input_builder.build_from_txt(book_id, source_path)
            self.set_book_indexing(book_id, "indexing", 0.20)

            self.graphrag_prompt_manager.ensure_prompts(book_id)
            self.graphrag_settings_builder.build(book_id)
            self.set_book_indexing(book_id, "indexing", 0.30)

            result = self.graphrag_index_runner.run(book_id)
            if not result["success"]:
                raise RuntimeError(f"GraphRAG index failed: {result.get('error', 'unknown')}")
            self.set_book_indexing(book_id, "indexing", 0.85)

            validation = self.graphrag_table_validator.validate(book_id)
            self.set_book_indexing(book_id, "indexing", 0.90)

            table_sizes = self.graphrag_table_loader.table_sizes(book_id)
            self.set_book_indexing(book_id, "indexing", 0.92)

            self.graph_projector.build(book_id)
            self.timeline_projector.build(book_id)
            self.set_book_indexing(book_id, "indexing", 0.97)

            final_manifest = {
                "id": book_id,
                "title": title,
                "source_path": str(source_path),
                "source": manifest.get("source", "local"),
                "chapter_count": manifest.get("chapter_count", 0),
                "chunk_count": 0,
                "indexed": True,
                "status": "ready",
                "indexed_at": datetime.now().isoformat(),
                "index_progress": 1.0,
                "has_vector_index": True,
                "text_unit_count": table_sizes.get("text_units", 0),
                "entity_count": table_sizes.get("entities", 0),
                "relationship_count": table_sizes.get("relationships", 0),
                "community_count": table_sizes.get("communities", 0),
            }
            book_dir = self.repo._book_dir(book_id)
            book_dir.mkdir(parents=True, exist_ok=True)
            (book_dir / "manifest.json").write_text(
                json.dumps(final_manifest, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            self.repo._cache.pop(book_id, None)
            self.set_book_indexing(book_id, "ready", 1.0)

        except Exception as e:
            import sys
            print(f"[INDEX ERROR] {book_id}: {e}", file=sys.stderr, flush=True)
            logger.exception("GraphRAG indexing failed for %s", book_id)
            manifest = next((book for book in self.repo.list_books() if book["id"] == book_id), None)
            if manifest:
                manifest["status"] = "error"
                self.repo.update_book_manifest(book_id, manifest)
            self.set_book_indexing(book_id, "error", 0.0)

    def delete_book(self, book_id: str) -> dict[str, Any]:
        """删除书目及其关联 data"""
        manifest = next((book for book in self.repo.list_books() if book["id"] == book_id), None)
        if not manifest:
            raise FileNotFoundError(f"Book {book_id} not found")

        if manifest.get("status") == "indexing":
            raise ValueError("Cannot delete book while it is indexing")


        # 删除索引目录
        index_path = self.config.data_dir / "books" / book_id
        if index_path.exists():
            import shutil
            shutil.rmtree(index_path)

        # 如果是上传的书籍，删除源文件
        if manifest.get("source") == "upload":
            source_path = manifest.get("source_path")
            if source_path:
                p = Path(source_path)
                if p.exists():
                    p.unlink()

        # 从 manifest 列表中移除
        self.repo.remove_book(book_id)

        return {"success": True, "book_id": book_id}

    def ensure_indexed(self, book_id: str) -> None:
        """Verify a book has been indexed. Raises FileNotFoundError if not."""
        manifest = next((book for book in self.repo.list_books() if book["id"] == book_id), None)
        if not manifest or not manifest.get("indexed"):
            raise FileNotFoundError(
                f"Book {book_id} is not indexed yet. "
                "Please click 'Start Analysis' in the console first."
            )
