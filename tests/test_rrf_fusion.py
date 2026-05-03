"""Tests for RRF (Reciprocal Rank Fusion) implementation."""
import pytest

from novel_system.search.orchestrator import reciprocal_rank_fusion


class TestReciprocalRankFusion:
    """Tests for RRF algorithm."""

    def test_rrf_basic(self):
        """Test basic RRF fusion with two channels."""
        candidates = [
            {"target": "chapter_chunks", "document_id": "doc1", "document": {"text": "a"}, "score": 0.9, "channel": "dense"},
            {"target": "chapter_chunks", "document_id": "doc2", "document": {"text": "b"}, "score": 0.8, "channel": "dense"},
            {"target": "chapter_chunks", "document_id": "doc1", "document": {"text": "a"}, "score": 0.5, "channel": "sparse"},
            {"target": "chapter_chunks", "document_id": "doc3", "document": {"text": "c"}, "score": 0.4, "channel": "sparse"},
        ]

        results = reciprocal_rank_fusion(candidates, k=60)

        # doc1 appears in both channels, should have highest RRF score
        assert results[0]["document_id"] == "doc1"

        # RRF score = 1/(60+1) + 1/(60+1) = 2/61 for doc1 (rank 1 in both)
        expected_doc1_score = 1 / 61 + 1 / 61
        assert abs(results[0]["score"] - expected_doc1_score) < 0.001

    def test_rrf_single_channel(self):
        """Test RRF with single channel (no fusion needed)."""
        candidates = [
            {"target": "t", "document_id": "doc1", "document": {}, "score": 0.9, "channel": "dense"},
            {"target": "t", "document_id": "doc2", "document": {}, "score": 0.8, "channel": "dense"},
            {"target": "t", "document_id": "doc3", "document": {}, "score": 0.7, "channel": "dense"},
        ]

        results = reciprocal_rank_fusion(candidates, k=60)

        # Order preserved by original score
        assert results[0]["document_id"] == "doc1"
        assert results[1]["document_id"] == "doc2"
        assert results[2]["document_id"] == "doc3"

    def test_rrf_empty_candidates(self):
        """Test RRF with empty input."""
        results = reciprocal_rank_fusion([], k=60)
        assert results == []

    def test_rrf_different_targets(self):
        """Test RRF with different targets (should not merge across targets)."""
        candidates = [
            {"target": "chapter_chunks", "document_id": "doc1", "document": {}, "score": 0.9, "channel": "dense"},
            {"target": "event_timeline", "document_id": "doc1", "document": {}, "score": 0.9, "channel": "dense"},
        ]

        results = reciprocal_rank_fusion(candidates, k=60)

        # Should not merge because targets are different
        assert len(results) == 2

    def test_rrf_k_parameter(self):
        """Test RRF with different k values."""
        candidates = [
            {"target": "t", "document_id": "doc1", "document": {}, "score": 0.9, "channel": "a"},
            {"target": "t", "document_id": "doc2", "document": {}, "score": 0.8, "channel": "a"},
            {"target": "t", "document_id": "doc1", "document": {}, "score": 0.7, "channel": "b"},
        ]

        results_k60 = reciprocal_rank_fusion(candidates, k=60)
        results_k10 = reciprocal_rank_fusion(candidates, k=10)

        # Smaller k means larger scores for same rank combination
        assert results_k10[0]["score"] > results_k60[0]["score"]

    def test_rrf_three_channels(self):
        """Test RRF with three channels."""
        candidates = [
            {"target": "t", "document_id": "doc1", "document": {}, "score": 0.9, "channel": "dense"},
            {"target": "t", "document_id": "doc1", "document": {}, "score": 0.8, "channel": "sparse"},
            {"target": "t", "document_id": "doc1", "document": {}, "score": 1.0, "channel": "alias"},
        ]

        results = reciprocal_rank_fusion(candidates, k=60)

        # doc1 appears in 3 channels, all at rank 1
        # RRF score = 3 * (1/61)
        expected_score = 3 / 61
        assert abs(results[0]["score"] - expected_score) < 0.001
