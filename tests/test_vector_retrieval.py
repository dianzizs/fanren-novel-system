"""Tests for vector retrieval integration."""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import numpy as np

from novel_system.config import AppConfig
from novel_system.indexing import BookIndexRepository, LoadedBookIndex
from novel_system.retrieval import HybridRetriever
from novel_system.search.orchestrator import SearchOrchestrator
from novel_system.vector_store import FAISSVectorStore


class MockEmbeddingProvider:
    """Mock embedding provider for testing."""

    def __init__(self, dimension: int = 128):
        self._dimension = dimension
        self._call_count = 0

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Generate deterministic embeddings based on text hash."""
        self._call_count += 1
        results = []
        for text in texts:
            # Use hash to generate deterministic but varied vectors
            np.random.seed(hash(text) % (2**31))
            vector = np.random.randn(self._dimension).astype(np.float32)
            # Normalize
            vector = vector / np.linalg.norm(vector)
            results.append(vector.tolist())
        return results


def create_test_config(tmp_path: Path) -> AppConfig:
    """Create test configuration."""
    return AppConfig(
        root_dir=tmp_path,
        data_dir=tmp_path / "data",
        runtime_dir=tmp_path / "data" / "runtime",
        books_dir=tmp_path / "data" / "books",
        default_book_id="test-book",
        default_book_title="Test Book",
        default_book_path=tmp_path / "test.txt",
        minimax_api_key="",
        minimax_base_url="https://api.minimax.chat/v1",
        minimax_chat_model="MiniMax-m2.7-HighSpeed",
        embedding_provider="local_openvino",
        local_embedding_model="BAAI/bge-small-zh-v1.5",
        local_embedding_device="CPU",
        local_embedding_fallback_device="CPU",
        local_embedding_batch_size=32,
        local_embedding_normalize=True,
        local_embedding_cache_dir=tmp_path / "cache",
        trace_enabled=False,
        trace_log_level="INFO",
    )


def create_test_book_content() -> str:
    """Create test book content with chapters."""
    return """第1章 开始
韩立是一个普通的少年，生活在青牛镇。
他和张铁一起在七玄门学艺。
第2章 修炼
韩立开始修炼长春功。
墨大夫教导他医术和毒术。
第3章 考验
韩立通过了外门弟子的考验。
他获得了升仙令。
"""


def test_vector_index_build_and_load():
    """Test vector index building and loading."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        config = create_test_config(tmp_path)

        # Create test book file
        book_file = tmp_path / "test_book.txt"
        book_file.write_text(create_test_book_content(), encoding="utf-8")

        # Create repository with mock embedding provider
        embedding_provider = MockEmbeddingProvider(dimension=128)
        repo = BookIndexRepository(config, embedding_provider=embedding_provider)

        # Build index
        manifest = repo.build_from_txt("test-book", "Test Book", book_file)

        # Verify vector index was created
        assert manifest["has_vector_index"] is True
        assert manifest["indexed"] is True

        # Load the index
        loaded = repo.load("test-book")

        # Verify loaded index structure
        assert isinstance(loaded, LoadedBookIndex)
        assert loaded.manifest["id"] == "test-book"
        assert len(loaded.corpora) > 0

        # Verify vector_stores were populated
        assert len(loaded.vector_stores) > 0
        for corpus_name, vector_store in loaded.vector_stores.items():
            assert isinstance(vector_store, FAISSVectorStore)
            assert vector_store.count() > 0


def test_tfidf_only_retrieval():
    """Test retrieval with TF-IDF only (no vector index)."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        config = create_test_config(tmp_path)

        # Create test book file
        book_file = tmp_path / "test_book.txt"
        book_file.write_text(create_test_book_content(), encoding="utf-8")

        # Create repository WITHOUT embedding provider
        repo = BookIndexRepository(config, embedding_provider=None)

        # Build index (should not create vector index)
        manifest = repo.build_from_txt("test-book", "Test Book", book_file)

        # Verify no vector index
        assert manifest["has_vector_index"] is False

        # Load the index
        loaded = repo.load("test-book")

        # Verify vector_stores is empty
        assert len(loaded.vector_stores) == 0

        # Test TF-IDF retrieval
        retriever = HybridRetriever(loaded)
        hits = retriever.retrieve(
            query="韩立",
            targets=["chapter_chunks"],
            chapter_scope=[],
            top_k=5,
        )

        # Should get some results from TF-IDF
        assert len(hits) > 0


def test_hybrid_retrieval():
    """Test TF-IDF + vector hybrid retrieval."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        config = create_test_config(tmp_path)

        # Create test book file
        book_file = tmp_path / "test_book.txt"
        book_file.write_text(create_test_book_content(), encoding="utf-8")

        # Create repository with mock embedding provider
        embedding_provider = MockEmbeddingProvider(dimension=128)
        repo = BookIndexRepository(config, embedding_provider=embedding_provider)

        # Build index
        repo.build_from_txt("test-book", "Test Book", book_file)

        # Load the index
        loaded = repo.load("test-book")

        # Create retriever
        retriever = HybridRetriever(loaded)

        # Get query embedding
        query_embedding = embedding_provider.embed(["韩立修炼"])[0]

        # Test hybrid retrieval
        hits = retriever.retrieve(
            query="韩立修炼",
            targets=["chapter_chunks"],
            chapter_scope=[],
            top_k=5,
            query_embedding=query_embedding,
        )

        # Should get results from both TF-IDF and vector search
        assert len(hits) > 0


def test_fallback_when_vector_store_missing():
    """Test fallback to TF-IDF when vector store is missing."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        config = create_test_config(tmp_path)

        # Create test book file
        book_file = tmp_path / "test_book.txt"
        book_file.write_text(create_test_book_content(), encoding="utf-8")

        # Create repository WITHOUT embedding provider
        repo = BookIndexRepository(config, embedding_provider=None)

        # Build index (no vector index)
        repo.build_from_txt("test-book", "Test Book", book_file)

        # Load the index
        loaded = repo.load("test-book")

        # Create orchestrator
        orchestrator = SearchOrchestrator()

        # Try to search with query_embedding but no vector store
        hits = orchestrator.retrieve(
            book_index=loaded,
            query="韩立",
            targets=["chapter_chunks"],
            chapter_scope=[],
            top_k=5,
            query_embedding=[0.1] * 128,  # Dummy embedding
        )

        # Should still get results from TF-IDF
        assert len(hits) > 0


def test_dense_search_method():
    """Test the _dense_search method directly."""
    orchestrator = SearchOrchestrator()

    # Test with None vector store
    result = orchestrator._dense_search(
        query_vector=[0.1] * 128,
        vector_store=None,
        target="test",
        top_k=5,
    )
    assert result == []

    # Test with actual vector store
    vector_store = FAISSVectorStore(dimension=128, metric="ip")

    # Add some test vectors
    test_docs = [
        {"id": "doc-1", "text": "测试文档一"},
        {"id": "doc-2", "text": "测试文档二"},
        {"id": "doc-3", "text": "测试文档三"},
    ]

    np.random.seed(42)
    vectors = np.random.randn(3, 128).astype(np.float32)
    vectors = vectors / np.linalg.norm(vectors, axis=1, keepdims=True)

    vector_store.add(
        ids=["doc-1", "doc-2", "doc-3"],
        vectors=vectors.tolist(),
        documents=test_docs,
    )

    # Search with a similar vector
    query_vector = vectors[0].tolist()  # Use first vector as query
    result = orchestrator._dense_search(
        query_vector=query_vector,
        vector_store=vector_store,
        target="test",
        top_k=3,
    )

    # Should get results
    assert len(result) > 0
    assert result[0]["target"] == "test"
    assert "document_id" in result[0]
    assert "document" in result[0]
    assert "score" in result[0]


def test_vector_index_persistence():
    """Test vector index persistence to disk."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        config = create_test_config(tmp_path)

        # Create test book file
        book_file = tmp_path / "test_book.txt"
        book_file.write_text(create_test_book_content(), encoding="utf-8")

        # Create repository with mock embedding provider
        embedding_provider = MockEmbeddingProvider(dimension=128)
        repo = BookIndexRepository(config, embedding_provider=embedding_provider)

        # Build index
        repo.build_from_txt("test-book", "Test Book", book_file)

        # Verify vector files exist
        book_dir = config.books_dir / "test-book"
        vectors_dir = book_dir / "vectors"
        assert vectors_dir.exists()

        # Check at least one corpus has vector files
        corpus_dirs = list(vectors_dir.iterdir())
        assert len(corpus_dirs) > 0

        # Verify FAISS index files
        for corpus_dir in corpus_dirs:
            assert (corpus_dir / "index.faiss").exists()
            assert (corpus_dir / "metadata.json").exists()
