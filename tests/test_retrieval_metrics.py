"""Tests for retrieval evaluation metrics."""
import pytest
from scripts.eval_retrieval import (
    recall_at_k,
    mrr_at_k,
    ndcg_at_k,
    dcg_at_k,
)


class TestRecallAtK:
    """Test recall@k metric."""

    def test_perfect_recall(self):
        """All relevant docs in top K should give recall 1.0."""
        retrieved = ["doc1", "doc2", "doc3", "doc4"]
        relevant = {"doc1", "doc2"}
        assert recall_at_k(retrieved, relevant, k=4) == 1.0

    def test_partial_recall(self):
        """Only some relevant docs in top K."""
        retrieved = ["doc1", "doc5", "doc3", "doc4"]
        relevant = {"doc1", "doc2", "doc3"}
        # Only doc1 and doc3 in top 4, so 2/3
        assert recall_at_k(retrieved, relevant, k=4) == pytest.approx(2/3, rel=1e-4)

    def test_no_relevant_in_top_k(self):
        """No relevant docs in top K should give recall 0."""
        retrieved = ["doc5", "doc6", "doc7"]
        relevant = {"doc1", "doc2"}
        assert recall_at_k(retrieved, relevant, k=3) == 0.0

    def test_empty_relevant(self):
        """Empty relevant set should return 0."""
        retrieved = ["doc1", "doc2"]
        relevant = set()
        assert recall_at_k(retrieved, relevant, k=2) == 0.0

    def test_k_smaller_than_retrieved(self):
        """K smaller than retrieved list should only check first K."""
        retrieved = ["doc1", "doc2", "doc3", "doc4"]
        relevant = {"doc3", "doc4"}
        # Only doc1, doc2 in top 2, so 0/2
        assert recall_at_k(retrieved, relevant, k=2) == 0.0


class TestMRRAtK:
    """Test MRR@k metric."""

    def test_first_result_relevant(self):
        """Relevant doc at position 1 should give MRR 1.0."""
        retrieved = ["doc1", "doc2", "doc3"]
        relevant = {"doc1"}
        assert mrr_at_k(retrieved, relevant, k=3) == 1.0

    def test_second_result_relevant(self):
        """Relevant doc at position 2 should give MRR 0.5."""
        retrieved = ["doc5", "doc1", "doc3"]
        relevant = {"doc1"}
        assert mrr_at_k(retrieved, relevant, k=3) == 0.5

    def test_third_result_relevant(self):
        """Relevant doc at position 3 should give MRR 1/3."""
        retrieved = ["doc5", "doc6", "doc1"]
        relevant = {"doc1"}
        assert mrr_at_k(retrieved, relevant, k=3) == pytest.approx(1/3, rel=1e-4)

    def test_no_relevant_in_top_k(self):
        """No relevant in top K should give MRR 0."""
        retrieved = ["doc5", "doc6", "doc7"]
        relevant = {"doc1"}
        assert mrr_at_k(retrieved, relevant, k=3) == 0.0

    def test_empty_relevant(self):
        """Empty relevant set should return 0."""
        retrieved = ["doc1", "doc2"]
        relevant = set()
        assert mrr_at_k(retrieved, relevant, k=2) == 0.0


class TestNDCGAtK:
    """Test nDCG@k metric."""

    def test_perfect_ndcg(self):
        """All relevant docs in top K should give nDCG 1.0."""
        retrieved = ["doc1", "doc2", "doc3"]
        relevant = {"doc1", "doc2", "doc3"}
        assert ndcg_at_k(retrieved, relevant, k=3) == 1.0

    def test_partial_ndcg(self):
        """Some relevant docs should give partial nDCG."""
        retrieved = ["doc1", "doc5", "doc2"]
        relevant = {"doc1", "doc2"}
        # DCG = 1 + 0/log2(3) + 1/log2(4) = 1 + 0 + 0.5 = 1.5
        # IDCG = 1 + 1/log2(3) = 1 + 0.631 = 1.631
        # nDCG = 1.5 / 1.631 ≈ 0.92
        assert ndcg_at_k(retrieved, relevant, k=3) > 0.9

    def test_no_relevant_in_top_k(self):
        """No relevant in top K should give nDCG 0."""
        retrieved = ["doc5", "doc6", "doc7"]
        relevant = {"doc1", "doc2"}
        assert ndcg_at_k(retrieved, relevant, k=3) == 0.0

    def test_empty_relevant(self):
        """Empty relevant set should return 0."""
        retrieved = ["doc1", "doc2"]
        relevant = set()
        assert ndcg_at_k(retrieved, relevant, k=2) == 0.0


class TestDCGAtK:
    """Test DCG@k metric."""

    def test_dcg_calculation(self):
        """Test DCG formula."""
        # relevances = [1, 0, 1]
        # DCG = 1 + 0/log2(2) + 1/log2(4) = 1 + 0 + 0.5 = 1.5
        relevances = [1, 0, 1]
        assert dcg_at_k(relevances, k=3) == pytest.approx(1.5, rel=1e-4)

    def test_dcg_all_ones(self):
        """All ones should give sum of diminishing gains."""
        relevances = [1, 1, 1]
        # DCG = 1 + 1/log2(3) + 1/log2(4) = 1 + 0.631 + 0.5 = 2.131
        assert dcg_at_k(relevances, k=3) == pytest.approx(2.131, rel=0.01)

    def test_dcg_empty(self):
        """Empty list should give 0."""
        assert dcg_at_k([], k=3) == 0.0
