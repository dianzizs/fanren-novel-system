from __future__ import annotations

import json
import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from ..models import BookInfo

logger = logging.getLogger(__name__)


class IndexingServiceMixin:
    """Mixin for book indexing operations."""

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
                )
            )
        return books

    def get_book_status(self, book_id: str) -> dict[str, Any]:
        """获取书籍索引状态"""
        manifest = next((book for book in self.repo.list_books() if book["id"] == book_id), None)
        if not manifest:
            raise FileNotFoundError(f"Book {book_id} not found")
        return {
            "book_id": book_id,
            "status": manifest.get("status", "pending"),
            "progress": manifest.get("index_progress", 0.0),
            "message": self._get_status_message(manifest),
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

    def start_book_index(self, book_id: str) -> dict[str, Any]:
        """异步启动书籍索引构建。

        在后台线程中执行索引构建，包括章节解析、切片、向量化等步骤。
        可通过 get_book_status() 查询进度。

        Args:
            book_id: 书籍 ID

        Returns:
            包含 status 和 message 的状态字典
        """
        manifest = next((book for book in self.repo.list_books() if book["id"] == book_id), None)
        if not manifest:
            raise FileNotFoundError(f"Book {book_id} not found")

        if manifest.get("status") == "indexing":
            return {"status": "indexing", "message": "正在分析中"}

        if manifest.get("status") == "ready":
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
        """后台执行书籍索引，分步骤更新进度。

        构建过程包括：
        1. 章节解析和切片
        2. TF-IDF 向量化
        3. FAISS 向量索引构建（如果 embedding_provider 可用）
        4. manifest 更新
        """
        try:
            manifest = next((book for book in self.repo.list_books() if book["id"] == book_id), None)
            if not manifest:
                return
            source_path = Path(manifest["source_path"])
            title = manifest["title"]

            # Create token callback for tracking LLM usage
            def token_callback(usage):
                self._record_token_usage(book_id, usage)

            self.set_book_indexing(book_id, "indexing", 0.05)
            raw_text = source_path.read_text(encoding="utf-8")

            self.set_book_indexing(book_id, "indexing", 0.10)
            chapters = self.repo._parse_chapters(raw_text)

            self.repo.prewarm_llm_extractions(chapters, book_id, token_callback)

            self.set_book_indexing(book_id, "indexing", 0.20)
            chunks = self.repo._build_chunks(chapters)

            self.set_book_indexing(book_id, "indexing", 0.30)
            chapter_summaries = self.repo._build_chapter_summaries(chapters)

            self.set_book_indexing(book_id, "indexing", 0.40)
            events = self.repo._build_event_timeline(chapters, chapter_summaries)

            self.set_book_indexing(book_id, "indexing", 0.50)
            character_cards = self.repo._build_character_cards(chapters, book_id, token_callback)

            self.set_book_indexing(book_id, "indexing", 0.55)
            character_registry = self.repo._build_character_registry(chapters, character_cards, book_id, token_callback)

            self.set_book_indexing(book_id, "indexing", 0.60)
            relationships = self.repo._build_relationships(chapters, character_cards)

            self.set_book_indexing(book_id, "indexing", 0.65)
            world_rules = self.repo._build_world_rules(chapters)

            self.set_book_indexing(book_id, "indexing", 0.70)
            canon_memory = self.repo._build_canon_memory(chapter_summaries, events)

            self.set_book_indexing(book_id, "indexing", 0.75)
            style_samples = self.repo._build_style_samples(chapters)

            self.set_book_indexing(book_id, "indexing", 0.80)
            recent_plot = self.repo._build_recent_plot_docs(chapters, chapter_summaries)

            corpora = {
                "chapter_chunks": chunks,
                "chapter_summaries": chapter_summaries,
                "event_timeline": events,
                "character_card": character_cards,
                "character_registry": character_registry,
                "relationship_graph": relationships,
                "world_rule": world_rules,
                "canon_memory": canon_memory,
                "recent_plot": recent_plot,
                "style_samples": style_samples,
                "vision_parse": [],
            }

            book_dir = self.repo._book_dir(book_id)
            book_dir.mkdir(parents=True, exist_ok=True)
            (book_dir / "chapters.json").write_text(
                json.dumps(chapters, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            self.set_book_indexing(book_id, "indexing", 0.82)
            total = len(corpora)
            for idx, (name, docs) in enumerate(corpora.items()):
                (book_dir / f"{name}.json").write_text(
                    json.dumps(docs, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                self.set_book_indexing(book_id, "indexing", 0.82 + 0.14 * (idx / total))

            for idx, (name, docs) in enumerate(corpora.items()):
                self.repo._build_vector_payload_for_corpus(book_id, name, docs)
                self.set_book_indexing(book_id, "indexing", 0.96 + 0.04 * (idx / total))

            # 构建并保存向量索引（委托给 repo 共享方法）
            has_vector_index = self.repo._build_vector_indexes(book_id, corpora)

            final_manifest = {
                "id": book_id,
                "title": title,
                "source_path": str(source_path),
                "source": manifest.get("source", "local"),
                "chapter_count": len(chapters),
                "chunk_count": len(chunks),
                "indexed": True,
                "status": "ready",
                "indexed_at": datetime.now().isoformat(),
                "index_progress": 1.0,
                "has_vector_index": has_vector_index,
            }
            (book_dir / "manifest.json").write_text(
                json.dumps(final_manifest, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            self.repo._cache.pop(book_id, None)

        except Exception as e:
            import sys
            print(f"[INDEX ERROR] {book_id}: {e}", file=sys.stderr, flush=True)
            manifest = next((book for book in self.repo.list_books() if book["id"] == book_id), None)
            if manifest:
                manifest["status"] = "error"
                self.repo.update_book_manifest(book_id, manifest)

    def delete_book(self, book_id: str) -> dict[str, Any]:
        """删除书目及其关联 data"""
        manifest = next((book for book in self.repo.list_books() if book["id"] == book_id), None)
        if not manifest:
            raise FileNotFoundError(f"Book {book_id} not found")

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

    def index_default_book(self) -> dict[str, Any]:
        return self.index_book(
            self.config.default_book_id,
            self.config.default_book_title,
            self.config.default_book_path,
        )

    def index_book(self, book_id: str, title: str | None = None, source_path: Path | None = None) -> dict[str, Any]:
        title = title or self.config.default_book_title
        source_path = source_path or self.config.default_book_path
        manifest = self.repo.build_from_txt(book_id, title, source_path)
        return manifest

    def ensure_indexed(self, book_id: str) -> None:
        manifest = next((book for book in self.repo.list_books() if book["id"] == book_id), None)
        if not manifest or not manifest.get("indexed"):
            if book_id != self.config.default_book_id:
                raise FileNotFoundError(f"Book {book_id} is not indexed")
            self.index_default_book()
