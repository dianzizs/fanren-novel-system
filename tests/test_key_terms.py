"""Tests for SearchOrchestrator._extract_key_terms."""

from __future__ import annotations

from novel_system.search.orchestrator import SearchOrchestrator


class TestExtractKeyTerms:
    """Unit tests for _extract_key_terms."""

    def setup_method(self) -> None:
        self.orchestrator = SearchOrchestrator()

    def test_extracts_nouns_from_chinese_query(self) -> None:
        """Nouns with >= 2 chars should be extracted."""
        terms = self.orchestrator._extract_key_terms("韩立的修为怎么样")
        # "韩立" (person name), "修为" (noun) should appear
        assert any("韩立" in t for t in terms), f"Expected '韩立' in {terms}"
        assert any("修为" in t for t in terms), f"Expected '修为' in {terms}"

    def test_extracts_quoted_terms(self) -> None:
        """Quoted content should be extracted as exact terms."""
        terms = self.orchestrator._extract_key_terms("「墨大夫」是什么身份")
        assert "墨大夫" in terms, f"Expected '墨大夫' in {terms}"

    def test_extracts_double_quoted_terms(self) -> None:
        """Content inside standard double quotes should be extracted."""
        terms = self.orchestrator._extract_key_terms('"炼气期"是什么阶段')
        assert "炼气期" in terms, f"Expected '炼气期' in {terms}"

    def test_filters_stopwords(self) -> None:
        """Stopwords like 什么, 的, 了 should not appear in results."""
        terms = self.orchestrator._extract_key_terms("这是什么时候的事情")
        stopwords = {"什么", "时候", "是", "在", "的", "了", "吗", "呢", "啊"}
        for term in terms:
            assert term not in stopwords, f"Stopword '{term}' should be filtered from {terms}"

    def test_returns_empty_for_pure_stopword_query(self) -> None:
        """A query consisting only of stopwords should return an empty list."""
        terms = self.orchestrator._extract_key_terms("的了吗呢啊")
        assert terms == [], f"Expected empty list, got {terms}"

    def test_deduplicates_terms(self) -> None:
        """Same term appearing multiple times should appear only once."""
        terms = self.orchestrator._extract_key_terms("韩立和韩立的故事")
        assert terms.count("韩立") <= 1, f"Expected deduplication, got {terms}"

    def test_short_words_excluded(self) -> None:
        """Single-character words should be excluded."""
        terms = self.orchestrator._extract_key_terms("他是谁")
        for term in terms:
            assert len(term) >= 2, f"Term '{term}' is shorter than 2 chars"
