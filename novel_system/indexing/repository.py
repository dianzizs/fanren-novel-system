from __future__ import annotations
import json
import logging
import pickle
import shutil
import time
from pathlib import Path
from typing import Any, Optional, TYPE_CHECKING

from .models import LoadedBookIndex
from .parser import parse_chapters
try:
    from .vector_indexing import load_vector_stores
except ImportError:
    from ..legacy.old_rag.indexing.vector_indexing import load_vector_stores

if TYPE_CHECKING:
    from ..embedding.base import EmbeddingProvider
    from ..config import AppConfig
    from ..llm import MiniMaxClient

logger = logging.getLogger(__name__)

class BookIndexRepository:
    """书籍索引仓库，管理索引的构建、加载和查询。

    提供从原始文本构建索引、加载已构建索引、读取索引制品等功能。
    """

    def __init__(
        self,
        config: AppConfig,
        embedding_provider: Optional["EmbeddingProvider"] = None,
    ) -> None:
        self.config = config
        self._embedding_provider = embedding_provider
        self._cache: dict[str, LoadedBookIndex] = {}

    def list_books(self) -> list[dict[str, Any]]:
        books: list[dict[str, Any]] = []
        if not self.config.books_dir.exists():
            return books
        for manifest_path in sorted(self.config.books_dir.glob("*/manifest.json")):
            for attempt in range(3):
                try:
                    with manifest_path.open("r", encoding="utf-8") as handle:
                        books.append(json.load(handle))
                    break
                except json.JSONDecodeError:
                    logger.warning(f"JSONDecodeError reading {manifest_path}, attempt {attempt + 1}/3")
                    if attempt == 2:
                        raise
                    time.sleep(0.01)
        return books

    def remove_book(self, book_id: str) -> None:
        """从 manifest 中移除书目"""
        book_dir = self._book_dir(book_id)
        if not book_dir.exists():
            return
        shutil.rmtree(book_dir)

    def update_book_manifest(self, book_id: str, manifest: dict[str, Any]) -> None:
        """更新书籍 manifest"""
        book_dir = self._book_dir(book_id)
        manifest_path = book_dir / "manifest.json"
        if not manifest_path.exists():
            return
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    def ensure_book_manifest(
        self,
        book_id: str,
        title: str,
        source_path: str,
        source: str = "local",
        status: str = "pending",
        reset_existing: bool = False,
    ) -> dict[str, Any]:
        book_dir = self._book_dir(book_id)
        book_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = book_dir / "manifest.json"
        if manifest_path.exists():
            if reset_existing:
                shutil.rmtree(book_dir)
                book_dir.mkdir(parents=True, exist_ok=True)
                self._cache.pop(book_id, None)
            else:
                with manifest_path.open("r", encoding="utf-8") as handle:
                    return json.load(handle)
        manifest = {
            "id": book_id,
            "title": title,
            "source_path": source_path,
            "source": source,
            "status": status,
            "chapter_count": 0,
            "chunk_count": 0,
            "indexed": False,
            "indexed_at": None,
            "index_progress": 0.0,
        }
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        return manifest

    def prepare_chapters(self, book_id: str, source_path: str) -> list[dict[str, Any]]:
        """Parse chapters from source text and save chapters.json early.

        Called during book registration so the reader UI can show the chapter
        list before GraphRAG indexing completes.
        """
        source = Path(source_path)
        try:
            raw_text = source.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            raw_text = source.read_text(encoding="gb18030")
        chapters = self._parse_chapters(raw_text)
        book_dir = self._book_dir(book_id)
        book_dir.mkdir(parents=True, exist_ok=True)
        (book_dir / "chapters.json").write_text(
            json.dumps(chapters, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        manifest_path = book_dir / "manifest.json"
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["chapter_count"] = len(chapters)
            manifest_path.write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        return chapters

    def read_artifact(self, book_id: str, artifact_name: str) -> Any:
        filenames = {
            "manifest": "manifest.json",
            "chapters": "chapters.json",
        }
        filename = filenames.get(artifact_name)
        if not filename:
            raise FileNotFoundError(f"Artifact {artifact_name} is not supported")
        path = self._book_dir(book_id) / filename
        if not path.exists():
            raise FileNotFoundError(f"Artifact {artifact_name} not found for {book_id}")
        return json.loads(path.read_text(encoding="utf-8"))

    @property
    def llm(self) -> "MiniMaxClient":
        from ..llm import MiniMaxClient
        return MiniMaxClient(self.config)

    def load(self, book_id: str) -> LoadedBookIndex:
        if book_id in self._cache:
            return self._cache[book_id]
        book_dir = self._book_dir(book_id)
        manifest_path = book_dir / "manifest.json"
        if not manifest_path.exists():
            raise FileNotFoundError(f"Book manifest not found for {book_id}")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        chapters = json.loads((book_dir / "chapters.json").read_text(encoding="utf-8"))
        corpora: dict[str, list[dict[str, Any]]] = {}
        vectorizers: dict[str, Any] = {}
        matrices: dict[str, Any] = {}
        for json_path in book_dir.glob("*.json"):
            if json_path.name in {"manifest.json", "chapters.json"}:
                continue
            name = json_path.stem
            corpora[name] = json.loads(json_path.read_text(encoding="utf-8"))
            pkl_path = book_dir / f"{name}.pkl"
            if pkl_path.exists():
                with pkl_path.open("rb") as handle:
                    payload = pickle.load(handle)
                vectorizers[name] = payload["vectorizer"]
                matrices[name] = payload["matrix"]

        # 加载向量索引（使用配置的向量存储目录）
        vector_stores = load_vector_stores(book_id, self.config)

        # Load NetworkX graph for GraphRAG
        graph = None
        graph_path = book_dir / "graph.json"
        if graph_path.exists():
            try:
                import networkx as nx
                graph_data = json.loads(graph_path.read_text(encoding="utf-8"))
                graph = nx.node_link_graph(graph_data)
                logger.info(f"Loaded NetworkX Graph for {book_id}")
            except Exception as e:
                logger.warning(f"Failed to load NetworkX Graph for {book_id}: {e}")

        loaded = LoadedBookIndex(
            manifest=manifest,
            chapters=chapters,
            corpora=corpora,
            vectorizers=vectorizers,
            matrices=matrices,
            vector_stores=vector_stores,
            graph=graph,
        )
        self._cache[book_id] = loaded
        return loaded

    def _book_dir(self, book_id: str) -> Path:
        return Path(self.config.books_dir) / book_id

    def _parse_chapters(self, raw_text: str) -> list[dict[str, Any]]:
        return parse_chapters(raw_text)
