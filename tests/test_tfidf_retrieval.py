"""Tests for TF-IDF retrieval in SearchOrchestrator."""
import pytest
from sklearn.feature_extraction.text import TfidfVectorizer
import numpy as np

from novel_system.search.orchestrator import SearchOrchestrator


class MockBookIndexWithTFIDF:
    """Mock book index with TF-IDF vectors for testing."""

    def __init__(self):
        self.corpora = {
            "chapter_chunks": [
                {
                    "id": "ch1-chunk0",
                    "chapter": 1,
                    "text": "韩立被村里人叫作二愣子，他性格沉稳，做事谨慎。",
                    "target": "chapter_chunks",
                },
                {
                    "id": "ch1-chunk1",
                    "chapter": 1,
                    "text": "墨大夫是七玄门的供奉，负责教导弟子修炼。",
                    "target": "chapter_chunks",
                },
                {
                    "id": "ch2-chunk0",
                    "chapter": 2,
                    "text": "韩立参加七玄门的内门弟子测试，是因为三叔的推举。",
                    "target": "chapter_chunks",
                },
            ],
        }
        # 构建词级 TF-IDF
        texts = [doc["text"] for doc in self.corpora["chapter_chunks"]]
        self.vectorizers = {
            "chapter_chunks": TfidfVectorizer(
                tokenizer=self._tokenize,
                lowercase=False,
                min_df=1,
            )
        }
        self.matrices = {
            "chapter_chunks": self.vectorizers["chapter_chunks"].fit_transform(texts)
        }

    def _tokenize(self, text: str) -> list[str]:
        """简单分词用于测试"""
        import jieba
        return list(jieba.cut(text))


class MockScopedBookIndexWithTFIDF:
    """Mock index where the in-scope relevant row is not row 0 in the full matrix."""

    def __init__(self):
        self.corpora = {
            "chapter_chunks": [
                {
                    "id": "ch1-noise",
                    "chapter": 1,
                    "text": "山边小村里炊烟升起，村民们正在闲谈。",
                    "target": "chapter_chunks",
                },
                {
                    "id": "ch2-target",
                    "chapter": 2,
                    "text": "韩立参加七玄门测试，是因为三叔推举并且内门待遇很好。",
                    "target": "chapter_chunks",
                },
                {
                    "id": "ch3-other",
                    "chapter": 3,
                    "text": "张铁在另一场考验中表现沉默。",
                    "target": "chapter_chunks",
                },
            ],
        }
        texts = [doc["text"] for doc in self.corpora["chapter_chunks"]]
        vectorizer = TfidfVectorizer(
            tokenizer=self._tokenize,
            lowercase=False,
            min_df=1,
        )
        self.vectorizers = {"chapter_chunks": vectorizer}
        self.matrices = {"chapter_chunks": vectorizer.fit_transform(texts)}
        self.vector_stores = {}

    def _tokenize(self, text: str) -> list[str]:
        import jieba
        return list(jieba.cut(text))


def test_tfidf_search_returns_relevant_results():
    """TF-IDF 检索应返回相关文档。"""
    orchestrator = SearchOrchestrator()
    index = MockBookIndexWithTFIDF()

    # 查询包含"韩立参加测试"
    hits = orchestrator.retrieve(
        book_index=index,
        query="韩立为什么参加测试",
        targets=["chapter_chunks"],
        chapter_scope=[],
        top_k=3,
    )

    # 应返回结果
    assert len(hits) > 0
    # 最相关的应该是包含"韩立参加测试"的文档
    top_hit = hits[0]
    assert "韩立" in top_hit.document.get("text", "")
    assert top_hit.score > 0


def test_tfidf_fallback_to_sparse_when_no_vectorizer():
    """无 TF-IDF 时应回退到字符级匹配。"""
    orchestrator = SearchOrchestrator()

    # 无 vectorizer 的 index
    class NoVectorIndex:
        corpora = {
            "chapter_chunks": [
                {"id": "ch1", "chapter": 1, "text": "韩立参加测试", "target": "chapter_chunks"}
            ]
        }
        vectorizers = {}
        matrices = {}

    index = NoVectorIndex()
    hits = orchestrator.retrieve(
        book_index=index,
        query="韩立",
        targets=["chapter_chunks"],
        chapter_scope=[],
        top_k=3,
    )

    # 应通过字符匹配返回结果
    assert len(hits) > 0


def test_tfidf_search_respects_chapter_scope():
    """TF-IDF 检索应遵循章节范围限制。"""
    orchestrator = SearchOrchestrator()
    index = MockBookIndexWithTFIDF()

    # 限制在第 1 章
    hits = orchestrator.retrieve(
        book_index=index,
        query="韩立",
        targets=["chapter_chunks"],
        chapter_scope=[1],
        top_k=3,
    )

    # 所有结果应在第 1 章
    for hit in hits:
        assert hit.document.get("chapter") == 1


def test_tfidf_search_keeps_matrix_rows_aligned_after_scope_filter():
    """章节过滤后，TF-IDF 分数应映射回原始 corpus 的正确文档。"""
    orchestrator = SearchOrchestrator()
    index = MockScopedBookIndexWithTFIDF()

    hits = orchestrator.retrieve(
        book_index=index,
        query="韩立为什么参加测试",
        targets=["chapter_chunks"],
        chapter_scope=[2],
        top_k=3,
    )

    assert hits
    assert hits[0].document["id"] == "ch2-target"
    assert hits[0].document["chapter"] == 2
    assert "三叔推举" in hits[0].document["text"]


def test_tfidf_search_dedupe_results():
    """TF-IDF 检索应去重。"""
    orchestrator = SearchOrchestrator()
    index = MockBookIndexWithTFIDF()

    hits = orchestrator.retrieve(
        book_index=index,
        query="韩立",
        targets=["chapter_chunks"],
        chapter_scope=[],
        top_k=10,
    )

    # 检查去重
    doc_ids = [h.document.get("id") for h in hits]
    assert len(doc_ids) == len(set(doc_ids))
