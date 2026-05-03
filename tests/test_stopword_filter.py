"""Tests for Chinese non-entity word filtering in validator.py.

US-008: Ensure common Chinese words (question words, pronouns, etc.)
are not matched as entities by the broad regex extraction.
"""

import pytest

from novel_system.validator import (
    CHINESE_NON_ENTITY_WORDS,
    AnswerValidator,
    ContinuationValidator,
    _filter_non_entities,
)


class TestFilterNonEntities:
    """Tests for the _filter_non_entities helper."""

    def test_question_words_filtered(self):
        """什么/怎么/为什么 etc. should not pass as entities."""
        words = ["什么", "怎么", "为什么", "哪里", "哪个", "多少", "何时", "如何", "为何", "哪些", "谁"]
        result = _filter_non_entities(words)
        assert result == [], f"Question words should be filtered, got: {result}"

    def test_pronouns_filtered(self):
        words = ["我们", "你们", "他们", "她们", "它们", "咱们", "自己", "大家", "别人"]
        result = _filter_non_entities(words)
        assert result == [], f"Pronouns should be filtered, got: {result}"

    def test_demonstratives_filtered(self):
        words = ["这个", "那个", "这些", "那些", "这样", "那样"]
        result = _filter_non_entities(words)
        assert result == [], f"Demonstratives should be filtered, got: {result}"

    def test_common_verbs_filtered(self):
        words = ["不是", "没有", "可以", "知道", "应该", "能够", "可能", "已经"]
        result = _filter_non_entities(words)
        assert result == [], f"Common verbs should be filtered, got: {result}"

    def test_conjunctions_filtered(self):
        words = ["但是", "然而", "因为", "所以", "如果", "虽然", "而且", "或者"]
        result = _filter_non_entities(words)
        assert result == [], f"Conjunctions should be filtered, got: {result}"

    def test_actual_entities_preserved(self):
        """Real entity names should pass through."""
        entities = ["韩立", "南宫婉", "墨大夫", "七玄门", "黄枫谷", "乱星海"]
        result = _filter_non_entities(entities)
        assert result == entities, f"Real entities should be preserved, got: {result}"

    def test_mixed_input(self):
        """Mix of entities and non-entities: only entities survive."""
        mixed = ["韩立", "什么", "南宫婉", "怎么", "七玄门", "为什么"]
        result = _filter_non_entities(mixed)
        assert result == ["韩立", "南宫婉", "七玄门"]

    def test_empty_input(self):
        assert _filter_non_entities([]) == []


class TestExtractKeywordsIntegration:
    """Integration tests for _extract_keywords with stopword filtering."""

    @pytest.fixture
    def validator(self):
        return AnswerValidator()

    def test_question_sentence_keywords(self, validator):
        """A question like '韩立为什么离开七玄门' should extract entities, not question words."""
        keywords = validator._extract_keywords("韩立为什么离开七玄门")
        # Should contain actual names
        assert "韩立" in keywords, f"Expected '韩立' in {keywords}"
        assert "七玄门" in keywords, f"Expected '七玄门' in {keywords}"
        # Should NOT contain question/function words
        non_entities = {"什么", "怎么", "为什么", "我们", "他们", "不是", "可以"}
        found_non_entities = non_entities & set(keywords)
        assert not found_non_entities, f"Non-entities leaked through: {found_non_entities}"

    def test_common_words_not_in_keywords(self, validator):
        """Verify that common non-entity words don't appear in extracted keywords."""
        test_cases = [
            "我们什么时候去那里",
            "他们怎么还不来",
            "为什么不能这样做",
            "你觉得怎么样",
        ]
        for text in test_cases:
            keywords = validator._extract_keywords(text)
            for bad_word in ["什么", "怎么", "为什么", "我们", "他们", "你们", "那个", "这个"]:
                assert bad_word not in keywords, (
                    f"'{bad_word}' should not be in keywords for '{text}', got: {keywords}"
                )
