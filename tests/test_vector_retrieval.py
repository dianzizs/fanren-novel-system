"""Tests for vector retrieval integration."""
from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np

from novel_system.config import AppConfig
from novel_system.indexing import BookIndexRepository, LoadedBookIndex
from novel_system.search.orchestrator import SearchOrchestrator
from novel_system.vector_store import FAISSVectorStore


def test_vector_index_build_and_load(tmp_app_dir: Path, test_config: AppConfig, mock_embedding_provider):
    """Test vector index building and loading."""
    # Create test book file
    book_file = tmp_app_dir / "test_book.txt"
    book_file.write_text("第1章 开始\n韩立是一个普通的少年，生活在青牛镇。\n", encoding="utf-8")

    # Create repository with mock embedding provider
    repo = BookIndexRepository(test_config, embedding_provider=mock_embedding_provider)

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


def test_tfidf_only_retrieval(tmp_app_dir: Path, test_config: AppConfig):
    """Test retrieval with TF-IDF only (no vector index)."""
    book_file = tmp_app_dir / "test_book.txt"
    book_file.write_text("第1章 开始\n韩立是一个普通的少年，生活在青牛镇。\n", encoding="utf-8")

    # Create repository WITHOUT embedding provider
    repo = BookIndexRepository(test_config, embedding_provider=None)
    manifest = repo.build_from_txt("test-book", "Test Book", book_file)

    assert manifest["has_vector_index"] is False

    loaded = repo.load("test-book")
    assert len(loaded.vector_stores) == 0

    orchestrator = SearchOrchestrator()
    hits = orchestrator.retrieve(
        book_index=loaded,
        query="韩立",
        targets=["chapter_chunks"],
        chapter_scope=[],
        top_k=5,
    )

    assert len(hits) > 0


def test_hybrid_retrieval(tmp_app_dir: Path, test_config: AppConfig, mock_embedding_provider):
    """Test TF-IDF + vector hybrid retrieval."""
    book_file = tmp_app_dir / "test_book.txt"
    book_file.write_text("第1章 开始\n韩立是一个普通的少年，生活在青牛镇。\n", encoding="utf-8")

    repo = BookIndexRepository(test_config, embedding_provider=mock_embedding_provider)
    repo.build_from_txt("test-book", "Test Book", book_file)
    loaded = repo.load("test-book")

    orchestrator = SearchOrchestrator()
    query_embedding = mock_embedding_provider.embed(["韩立"])[0]

    hits = orchestrator.retrieve(
        book_index=loaded,
        query="韩立",
        targets=["chapter_chunks"],
        chapter_scope=[],
        top_k=5,
        query_embedding=query_embedding,
    )

    assert len(hits) > 0


def test_fallback_when_vector_store_missing(tmp_app_dir: Path, test_config: AppConfig):
    """Test fallback to TF-IDF when vector store is missing."""
    book_file = tmp_app_dir / "test_book.txt"
    book_file.write_text("第1章 开始\n韩立是一个普通的少年，生活在青牛镇。\n", encoding="utf-8")

    repo = BookIndexRepository(test_config, embedding_provider=None)
    repo.build_from_txt("test-book", "Test Book", book_file)
    loaded = repo.load("test-book")

    orchestrator = SearchOrchestrator()
    hits = orchestrator.retrieve(
        book_index=loaded,
        query="韩立",
        targets=["chapter_chunks"],
        chapter_scope=[],
        top_k=5,
        query_embedding=[0.1] * 128,  # Dummy embedding
    )

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

    test_docs = [
        {"id": "doc-1", "text": "测试文档一"},
        {"id": "doc-2", "text": "测试文档二"},
    ]

    np.random.seed(42)
    vectors = np.random.randn(2, 128).astype(np.float32)
    vectors = vectors / np.linalg.norm(vectors, axis=1, keepdims=True)

    vector_store.add(
        ids=["doc-1", "doc-2"],
        vectors=vectors.tolist(),
        documents=test_docs,
    )

    query_vector = vectors[0].tolist()
    result = orchestrator._dense_search(
        query_vector=query_vector,
        vector_store=vector_store,
        target="test",
        top_k=3,
    )

    assert len(result) > 0
    assert result[0]["target"] == "test"
    assert "document_id" in result[0]


def test_dense_search_respects_chapter_scope():
    """Dense retrieval must not return chapters outside the requested scope."""
    orchestrator = SearchOrchestrator()
    vector_store = FAISSVectorStore(dimension=3, metric="ip")

    vector_store.add(
        ids=["ch1", "ch2"],
        vectors=[[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
        documents=[
            {"id": "ch1", "chapter": 1, "text": "第一章"},
            {"id": "ch2", "chapter": 2, "text": "第二章"},
        ],
    )

    class ScopedVectorIndex:
        pass

    index = ScopedVectorIndex()
    index.corpora = {
        "chapter_chunks": [
            {"id": "ch1", "chapter": 1, "text": "第一章"},
            {"id": "ch2", "chapter": 2, "text": "第二章"},
        ]
    }
    index.vector_stores = {"chapter_chunks": vector_store}
    index.vectorizers = {}
    index.matrices = {}

    hits = orchestrator.retrieve(
        book_index=index,
        query="第二章",
        targets=["chapter_chunks"],
        chapter_scope=[1],
        top_k=2,
        query_embedding=[0.0, 1.0, 0.0],
    )

    assert hits
    assert all(hit.document["chapter"] == 1 for hit in hits)


def test_vector_index_persistence(tmp_app_dir: Path, test_config: AppConfig, mock_embedding_provider):
    """Test vector index persistence to disk."""
    book_file = tmp_app_dir / "test_book.txt"
    book_file.write_text("第1章 开始\n韩立是一个普通的少年，生活在青牛镇。\n", encoding="utf-8")

    repo = BookIndexRepository(test_config, embedding_provider=mock_embedding_provider)
    repo.build_from_txt("test-book", "Test Book", book_file)

    book_hash = hashlib.md5("test-book".encode()).hexdigest()[:12]
    vectors_dir = test_config.vector_store_dir / book_hash
    assert vectors_dir.exists()

    corpus_dirs = list(vectors_dir.iterdir())
    assert len(corpus_dirs) > 0

    for corpus_dir in corpus_dirs:
        assert (corpus_dir / "index.faiss").exists()
        assert (corpus_dir / "metadata.json").exists()
