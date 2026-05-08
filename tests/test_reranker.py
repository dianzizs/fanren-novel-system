"""Tests for the RuleBasedReranker."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from novel_system.reranker.rule_based import RuleBasedReranker
from novel_system.reranker.base import RerankResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@dataclass
class FakeHit:
    """Minimal stand-in for RetrievalHit."""
    target: str
    document: dict[str, Any]
    score: float


def _make_hit(
    text: str = "",
    target: str = "chapter_chunks",
    score: float = 0.5,
    chapter: int | None = None,
    **extra_doc: Any,
) -> FakeHit:
    doc: dict[str, Any] = {"text": text, **extra_doc}
    if chapter is not None:
        doc["chapter"] = chapter
    return FakeHit(target=target, document=doc, score=score)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRerankEmpty:
    def test_empty_candidates_returns_empty_list(self) -> None:
        reranker = RuleBasedReranker()
        assert reranker.rerank("任何查询", []) == []


class TestRerankSorting:
    def test_results_sorted_by_final_score(self) -> None:
        reranker = RuleBasedReranker()
        hit_low = _make_hit(text="无关内容", target="style_samples", score=0.1)
        hit_high = _make_hit(text="主角小明出现了", target="character_card", score=0.9)
        results = reranker.rerank("小明", [hit_low, hit_high])
        assert len(results) == 2
        assert results[0].final_score >= results[1].final_score
        assert results[0].rank == 1
        assert results[1].rank == 2


class TestEntityMatch:
    def test_entity_match_boosts_score(self) -> None:
        reranker = RuleBasedReranker()
        hit_with = _make_hit(text="小明是一个勇敢的少年", target="chapter_chunks", score=0.5)
        hit_without = _make_hit(text="无关的文本内容", target="chapter_chunks", score=0.5)
        res_with, res_without = reranker.rerank("小明", [hit_with, hit_without])
        assert res_with.final_score > res_without.final_score


class TestChapterRelevance:
    def test_doc_near_scope_center_scores_higher(self) -> None:
        reranker = RuleBasedReranker()
        scope = [10, 20]
        hit_center = _make_hit(text="文本", chapter=15, score=0.5)
        hit_edge = _make_hit(text="文本", chapter=10, score=0.5)
        res_center, res_edge = reranker.rerank("查询", [hit_center, hit_edge], scope=scope)
        assert res_center.final_score > res_edge.final_score


class TestTargetTypeWeights:
    def test_character_card_beats_recent_plot(self) -> None:
        reranker = RuleBasedReranker()
        hit_card = _make_hit(text="文本内容", target="character_card", score=0.5)
        hit_plot = _make_hit(text="文本内容", target="recent_plot", score=0.5)
        res_card, res_plot = reranker.rerank("查询", [hit_card, hit_plot])
        assert res_card.final_score > res_plot.final_score


class TestIsReady:
    def test_is_ready_returns_true(self) -> None:
        assert RuleBasedReranker().is_ready is True


class TestComputeChapterRelevance:
    """Direct tests for _compute_chapter_relevance edge cases."""

    def test_returns_zero_when_scope_is_none(self) -> None:
        reranker = RuleBasedReranker()
        assert reranker._compute_chapter_relevance({}, None) == 0.0

    def test_returns_zero_when_scope_is_empty(self) -> None:
        reranker = RuleBasedReranker()
        assert reranker._compute_chapter_relevance({}, []) == 0.0

    def test_returns_zero_when_no_chapter_info(self) -> None:
        reranker = RuleBasedReranker()
        assert reranker._compute_chapter_relevance({"text": "abc"}, [1, 10]) == 0.0

    def test_returns_one_when_chapter_equals_single_scope(self) -> None:
        reranker = RuleBasedReranker()
        assert reranker._compute_chapter_relevance({"chapter": 5}, [5]) == 1.0

    def test_uses_active_range_center(self) -> None:
        reranker = RuleBasedReranker()
        score = reranker._compute_chapter_relevance(
            {"active_range": [8, 12]}, [10, 20],
        )
        # center of [8,12] = 10, center of scope [10,20] = 15, distance=5, radius=5
        # relevance = 1 - 5/(5*2) = 0.5
        assert score == pytest.approx(0.5)
