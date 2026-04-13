"""Tests for search orchestrator and backends."""
from novel_system.search.orchestrator import SearchOrchestrator
from novel_system.search.base import RetrievalCandidate


class DummyBookIndex:
    """Mock book index for testing."""

    def __init__(self):
        self.corpora = {
            "character_card": [
                {
                    "id": "character-韩立",
                    "character_id": "char-韩立",
                    "canonical_name": "韩立",
                    "aliases": ["二愣子"],
                    "retrieval_text": "韩立 二愣子 村里人叫作二愣子",
                    "chapter": 1,
                    "target": "character_card",
                }
            ],
            "chapter_chunks": [
                {
                    "id": "ch1-chunk0",
                    "chapter": 1,
                    "text": "韩立被村里人叫作二愣子。",
                    "target": "chapter_chunks",
                }
            ],
        }
        self.vectorizers = {}
        self.matrices = {}


def test_exact_alias_match_beats_dense_fallback():
    """精确别名匹配应优先于稠密检索。"""
    orchestrator = SearchOrchestrator()
    index = DummyBookIndex()

    hits = orchestrator.retrieve(
        book_index=index,
        query="二愣子是谁",
        targets=["character_card"],
        chapter_scope=[1, 10],
        top_k=3,
    )

    assert len(hits) >= 1
    assert hits[0].document["character_id"] == "char-韩立"


def test_cross_target_dedupe_uses_target_and_document_id():
    """跨目标去重应使用 target 和 document_id。"""
    orchestrator = SearchOrchestrator()

    # Test the dedupe method directly
    candidates = [
        {"target": "chapter_chunks", "document_id": "a", "score": 0.8, "document": {}},
        {"target": "chapter_chunks", "document_id": "a", "score": 0.6, "document": {}},
    ]

    deduped = orchestrator._dedupe_candidates(candidates)

    assert len(deduped) == 1
    assert deduped[0]["score"] == 0.8


def test_retrieval_candidate_dataclass():
    """RetrievalCandidate 数据类应有正确的字段。"""
    candidate = RetrievalCandidate(
        target="character_card",
        document_id="character-韩立",
        document={"canonical_name": "韩立"},
        score=0.95,
    )

    assert candidate.target == "character_card"
    assert candidate.document_id == "character-韩立"
    assert candidate.score == 0.95
