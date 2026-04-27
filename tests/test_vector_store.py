"""Tests for FAISS Vector Store implementation."""
import tempfile
from pathlib import Path

import pytest

from novel_system.vector_store import FAISSVectorStore, VectorSearchResult


class TestFAISSVectorStore:
    """测试 FAISS 向量存储。"""

    def test_create_store(self):
        """测试创建存储。"""
        store = FAISSVectorStore(dimension=4, metric="ip")
        assert store.dimension == 4
        assert store.is_ready
        assert store.count() == 0

    def test_add_vectors(self):
        """测试添加向量。"""
        store = FAISSVectorStore(dimension=4, metric="ip")

        ids = ["doc1", "doc2", "doc3"]
        vectors = [[1, 0, 0, 0], [0, 1, 0, 0], [0.9, 0.1, 0, 0]]
        docs = [{"text": "doc1"}, {"text": "doc2"}, {"text": "doc3"}]

        count = store.add(ids, vectors, docs)
        assert count == 3
        assert store.count() == 3

    def test_add_duplicate_id(self):
        """测试添加重复 ID 应跳过。"""
        store = FAISSVectorStore(dimension=4)

        store.add(["doc1"], [[1, 0, 0, 0]], [{"text": "doc1"}])
        count = store.add(["doc1"], [[0, 1, 0, 0]], [{"text": "doc1-new"}])

        assert count == 0  # 应跳过
        assert store.count() == 1

    def test_search(self):
        """测试搜索。"""
        store = FAISSVectorStore(dimension=4, metric="ip")

        ids = ["doc1", "doc2", "doc3"]
        vectors = [[1, 0, 0, 0], [0, 1, 0, 0], [0.9, 0.1, 0, 0]]
        docs = [{"text": "doc1"}, {"text": "doc2"}, {"text": "doc3"}]
        store.add(ids, vectors, docs)

        # 搜索最接近 [1,0,0,0] 的向量
        results = store.search([1, 0, 0, 0], top_k=3)

        assert len(results) == 3
        # doc1 应该是最相似的
        assert results[0].id == "doc1"
        assert results[0].score > results[1].score

    def test_search_with_filter(self):
        """测试带过滤条件的搜索。"""
        store = FAISSVectorStore(dimension=4)

        ids = ["doc1", "doc2", "doc3"]
        vectors = [[1, 0, 0, 0], [1, 0, 0, 0], [1, 0, 0, 0]]
        docs = [
            {"text": "doc1", "category": "A"},
            {"text": "doc2", "category": "B"},
            {"text": "doc3", "category": "A"},
        ]
        store.add(ids, vectors, docs)

        results = store.search([1, 0, 0, 0], top_k=3, filter={"category": "A"})

        assert len(results) == 2
        for r in results:
            assert r.document["category"] == "A"

    def test_get(self):
        """测试根据 ID 获取。"""
        store = FAISSVectorStore(dimension=4)

        store.add(
            ["doc1", "doc2"],
            [[1, 0, 0, 0], [0, 1, 0, 0]],
            [{"text": "doc1"}, {"text": "doc2"}],
        )

        results = store.get(["doc1", "doc2", "nonexistent"])

        assert len(results) == 2
        ids = [r.id for r in results]
        assert "doc1" in ids
        assert "doc2" in ids

    def test_delete(self):
        """测试删除。"""
        store = FAISSVectorStore(dimension=4)

        store.add(
            ["doc1", "doc2", "doc3"],
            [[1, 0, 0, 0]] * 3,
            [{"text": f"doc{i}"} for i in range(1, 4)],
        )

        deleted = store.delete(["doc2", "nonexistent"])
        assert deleted == 1
        assert store.count() == 2

    def test_save_and_load(self):
        """测试保存和加载。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # 创建并保存
            store = FAISSVectorStore(dimension=4, metric="ip")
            store.add(
                ["doc1", "doc2"],
                [[1, 0, 0, 0], [0, 1, 0, 0]],
                [{"text": "doc1"}, {"text": "doc2"}],
            )
            store.save(tmpdir)

            # 加载到新实例
            store2 = FAISSVectorStore(dimension=4)
            store2.load(tmpdir)

            assert store2.count() == 2
            assert store2.dimension == 4

            results = store2.get(["doc1", "doc2"])
            assert len(results) == 2

    def test_empty_search(self):
        """测试空存储搜索。"""
        store = FAISSVectorStore(dimension=4)
        results = store.search([1, 0, 0, 0], top_k=10)
        assert results == []


class TestVectorSearchResult:
    """测试搜索结果数据类。"""

    def test_result_creation(self):
        """测试结果创建。"""
        result = VectorSearchResult(
            id="test-id",
            score=0.95,
            document={"text": "content"},
        )
        assert result.id == "test-id"
        assert result.score == 0.95
        assert result.document["text"] == "content"
