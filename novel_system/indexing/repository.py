from __future__ import annotations
import hashlib
import json
import logging
import pickle
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, TYPE_CHECKING

from .models import LoadedBookIndex
from .parser import parse_chapters, build_chunks, clean_line
from ..utils.text_utils import split_sentences, score_event_sentence
from ..utils.text_utils import score_event_sentence
from .scene import build_chapter_chunks
from .llm_extraction import (
    build_extraction_chunks,
    extract_structured_from_llm,
    prewarm_llm_extractions,
    filter_names_with_llm,
    extract_person_names,
)
try:
    from .vector_indexing import (
        tokenize_chinese,
        build_vector_payload,
        build_faiss_index,
        build_vector_indexes,
        load_vector_stores,
    )
except ImportError:
    from ..legacy.old_rag.indexing.vector_indexing import (
        tokenize_chinese,
        build_vector_payload,
        build_faiss_index,
        build_vector_indexes,
        load_vector_stores,
    )
from .artifact_builders import (
    build_chapter_summaries,
    build_event_timeline_from_chapters,
    build_character_cards_from_chapters,
    build_character_registry,
    build_relationships,
    build_world_rules,
    build_canon_memory,
    build_style_samples,
    build_recent_plot_docs,
)

if TYPE_CHECKING:
    from ..embedding.base import EmbeddingProvider
    from ..vector_store.base import BaseVectorStore
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
        self._active_llm_extractions: dict[int, list[Any]] = {}
        self._active_book_id: str = ""

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

    def read_artifact(self, book_id: str, artifact_name: str) -> Any:
        filenames = {
            "manifest": "manifest.json",
            "chapters": "chapters.json",
            "scene_segments": "scene_segments.json",
            "character_registry": "character_registry.json",
            "chapter_chunks": "chapter_chunks.json",
            "chapter_summaries": "chapter_summaries.json",
            "event_timeline": "event_timeline.json",
            "character_card": "character_card.json",
            "relationship_graph": "relationship_graph.json",
            "world_rule": "world_rule.json",
            "canon_memory": "canon_memory.json",
            "recent_plot": "recent_plot.json",
            "style_samples": "style_samples.json",
            "vision_parse": "vision_parse.json",
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

    def _build_extraction_chunks(self, chapter_text: str, chunk_size: int = 1800, overlap: int = 250) -> list[str]:
        return build_extraction_chunks(chapter_text, chunk_size, overlap)

    def _extract_structured_from_llm(
        self,
        chunk_text: str,
        token_callback: Optional[Any] = None,
    ) -> Optional[Any]:
        return extract_structured_from_llm(
            self.llm,
            chunk_text,
            self._book_dir(self._active_book_id) if self._active_book_id else None,
            self._active_book_id,
            token_callback,
        )

    def prewarm_llm_extractions(
        self,
        chapters: list[dict[str, Any]],
        book_id: str,
        token_callback: Optional[Any] = None,
    ) -> None:
        self._active_book_id = book_id
        self._active_llm_extractions = prewarm_llm_extractions(
            self.llm,
            chapters,
            book_id,
            self._book_dir(book_id),
            token_callback,
        )

    def build_from_txt(self, book_id: str, title: str, source_path: Path, token_callback: Optional[Any] = None) -> dict[str, Any]:
        raw_text = source_path.read_text(encoding="utf-8")
        chapters = self._parse_chapters(raw_text)
        
        # Warm up LLM extraction cache if enabled
        self.prewarm_llm_extractions(chapters, book_id, token_callback)
        
        chunks = self._build_chunks(chapters)
        chapter_summaries = self._build_chapter_summaries(chapters)
        events = self._build_event_timeline(chapters, chapter_summaries)
        character_cards = self._build_character_cards(chapters, book_id, token_callback)
        character_registry = self._build_character_registry(chapters, character_cards, book_id, token_callback)
        relationships = self._build_relationships(chapters, character_cards)
        world_rules = self._build_world_rules(chapters)
        canon_memory = self._build_canon_memory(chapter_summaries, events)
        style_samples = self._build_style_samples(chapters)
        recent_plot = self._build_recent_plot_docs(chapters, chapter_summaries)

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

        book_dir = self._book_dir(book_id)
        book_dir.mkdir(parents=True, exist_ok=True)
        (book_dir / "chapters.json").write_text(
            json.dumps(chapters, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        for name, docs in corpora.items():
            (book_dir / f"{name}.json").write_text(
                json.dumps(docs, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            payload = self._build_vector_payload(docs)
            with (book_dir / f"{name}.pkl").open("wb") as handle:
                pickle.dump(payload, handle)

        # Build and save NetworkX graph for GraphRAG
        try:
            import networkx as nx
            G = nx.Graph()
            for card in character_cards:
                name = card.get("name")
                if name:
                    G.add_node(
                        name,
                        canonical_name=card.get("canonical_name", name),
                        aliases=card.get("aliases", []),
                        first_chapter=card.get("chapter", 1),
                    )
            for rel in relationships:
                try:
                    title = rel.get("title", "")
                    if " / " in title:
                        left, right = title.split(" / ")
                        weight = rel.get("weight", 1)
                        G.add_edge(left, right, weight=weight, text=rel.get("text", ""))
                except Exception as e:
                    logger.warning(f"Failed to add edge to NetworkX graph: {e}")
            
            graph_data = nx.node_link_data(G)
            (book_dir / "graph.json").write_text(
                json.dumps(graph_data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            logger.info(f"Successfully saved NetworkX Graph to {book_dir / 'graph.json'}")
        except Exception as e:
            logger.error(f"Failed to build or save NetworkX graph: {e}", exc_info=True)

        # 构建并保存向量索引（如果提供了 embedding_provider）
        has_vector_index = self._build_vector_indexes(book_id, corpora)

        manifest = {
            "id": book_id,
            "title": title,
            "source_path": str(source_path),
            "chapter_count": len(chapters),
            "chunk_count": len(chunks),
            "indexed": True,
            "indexed_at": datetime.utcnow().isoformat(),
            "has_vector_index": has_vector_index,
        }
        (book_dir / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self._cache.pop(book_id, None)
        return manifest

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

    def _build_chunks(self, chapters: list[dict[str, Any]], chunk_size: int = 420, overlap: int = 80) -> list[dict[str, Any]]:
        return build_chunks(chapters, chunk_size, overlap)

    def _build_chapter_summaries(self, chapters: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return build_chapter_summaries(chapters)

    def _build_event_timeline(
        self,
        chapters: list[dict[str, Any]],
        chapter_summaries: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        return build_event_timeline_from_chapters(chapters, chapter_summaries, self._active_llm_extractions)

    def _build_character_cards(
        self,
        chapters: list[dict[str, Any]],
        book_id: str = "",
        token_callback: Optional[Any] = None,
    ) -> list[dict[str, Any]]:
        return build_character_cards_from_chapters(
            chapters, self.config, book_id, token_callback, self._active_llm_extractions
        )

    def _build_character_registry(
        self,
        chapters: list[dict[str, Any]],
        character_cards: list[dict[str, Any]],
        book_id: str = "",
        token_callback: Optional[Any] = None,
    ) -> list[dict[str, Any]]:
        return build_character_registry(
            chapters, character_cards, self.config, book_id, token_callback, self._active_llm_extractions
        )

    def _build_relationships(
        self,
        chapters: list[dict[str, Any]],
        character_cards: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        return build_relationships(
            chapters, character_cards, self.config, self._active_book_id, self._active_llm_extractions
        )

    def _build_world_rules(self, chapters: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return build_world_rules(chapters)

    def _build_canon_memory(
        self,
        chapter_summaries: list[dict[str, Any]],
        events: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        return build_canon_memory(chapter_summaries, events)

    def _build_style_samples(self, chapters: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return build_style_samples(chapters)

    def _build_recent_plot_docs(
        self,
        chapters: list[dict[str, Any]],
        chapter_summaries: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        return build_recent_plot_docs(chapters, chapter_summaries)

    @staticmethod
    def _tokenize_chinese(text: str) -> list[str]:
        return tokenize_chinese(text)

    def _build_vector_payload(self, docs: list[dict[str, Any]]) -> dict[str, Any]:
        return build_vector_payload(docs)

    def _build_faiss_index(
        self,
        docs: list[dict[str, Any]],
        embedding_provider: "EmbeddingProvider",
    ) -> Optional[Any]:
        return build_faiss_index(docs, embedding_provider)

    def _build_vector_indexes(self, book_id: str, corpora: dict[str, list[dict[str, Any]]]) -> bool:
        return build_vector_indexes(book_id, corpora, self.config, self._embedding_provider)

    def _build_vector_payload_for_corpus(self, book_id: str, corpus_name: str, docs: list[dict[str, Any]]) -> None:
        book_dir = self._book_dir(book_id)
        payload = build_vector_payload(docs)
        with (book_dir / f"{corpus_name}.pkl").open("wb") as handle:
            pickle.dump(payload, handle)

    def _clean_line(self, line: str) -> str:
        return clean_line(line)

    def _split_sentences(self, text: str) -> list[str]:
        return split_sentences(text)

    def _score_event_sentence(self, sentence: str) -> float:
        return score_event_sentence(sentence)

    def _filter_names_with_llm(self, names: list[str], batch_size: int = 50, token_callback: Optional[Any] = None) -> set[str]:
        return filter_names_with_llm(self.config, names, batch_size, token_callback)

    def _extract_person_names(self, text: str) -> list[str]:
        return extract_person_names(text)
