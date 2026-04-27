"""Tests for Planner intent-based routing."""
import pytest
from novel_system.planner import RuleBasedPlanner
from novel_system.models import QueryIntent, Scope, ConversationTurn


@pytest.fixture
def planner():
    return RuleBasedPlanner()


class TestIntentDetection:
    """测试意图检测。"""

    def test_detect_causal_chain_intent(self, planner):
        """因果链查询应检测为 CAUSAL_CHAIN。"""
        assert planner._detect_intent("韩立为什么参加测试") == QueryIntent.CAUSAL_CHAIN
        assert planner._detect_intent("怎么修炼象甲功") == QueryIntent.CAUSAL_CHAIN
        assert planner._detect_intent("原因是什么") == QueryIntent.CAUSAL_CHAIN

    def test_detect_fact_query_intent(self, planner):
        """事实查询应检测为 FACT_QUERY。"""
        assert planner._detect_intent("象甲功是什么") == QueryIntent.FACT_QUERY
        assert planner._detect_intent("七玄门有哪些堂口") == QueryIntent.FACT_QUERY

    def test_detect_character_analysis_intent(self, planner):
        """人物分析查询应检测为 CHARACTER_ANALYSIS。"""
        assert planner._detect_intent("韩立是谁") == QueryIntent.CHARACTER_ANALYSIS
        assert planner._detect_intent("韩立的性格怎么样") == QueryIntent.CHARACTER_ANALYSIS
        assert planner._detect_intent("墨大夫的外貌") == QueryIntent.CHARACTER_ANALYSIS

    def test_detect_summary_intent(self, planner):
        """总结查询应检测为 SUMMARY。"""
        assert planner._detect_intent("总结第一章") == QueryIntent.SUMMARY
        assert planner._detect_intent("概括韩立的经历") == QueryIntent.SUMMARY

    def test_detect_temporal_intent(self, planner):
        """时间相关查询应检测为 TEMPORAL。"""
        assert planner._detect_intent("韩立后来怎么样了") == QueryIntent.TEMPORAL
        assert planner._detect_intent("结局是什么") == QueryIntent.TEMPORAL

    def test_detect_general_intent(self, planner):
        """未匹配的查询应检测为 GENERAL。"""
        assert planner._detect_intent("韩立") == QueryIntent.GENERAL
        assert planner._detect_intent("七玄门") == QueryIntent.GENERAL


class TestIntentBasedRouting:
    """测试意图优先路由。"""

    def test_causal_query_not_prioritize_character_card(self, planner):
        """因果链查询不应优先检索 character_card。"""
        output, _ = planner.plan(
            query="韩立为什么参加七玄门测试",
            scope=Scope(),
            history=[],
        )

        # event_timeline 应该在前面
        assert "event_timeline" in output.retrieval_targets
        # character_card 不应在第一位
        if "character_card" in output.retrieval_targets:
            assert output.retrieval_targets[0] != "character_card"

    def test_character_analysis_prioritize_character_card(self, planner):
        """人物分析查询应优先检索 character_card。"""
        output, _ = planner.plan(
            query="韩立是谁",
            scope=Scope(),
            history=[],
        )

        # character_card 应该在第一位
        assert output.retrieval_targets[0] == "character_card"

    def test_fact_query_targets_chapter_chunks(self, planner):
        """事实查询应检索 chapter_chunks。"""
        output, _ = planner.plan(
            query="象甲功是什么",
            scope=Scope(),
            history=[],
        )

        assert "chapter_chunks" in output.retrieval_targets

    def test_temporal_query_targets_event_timeline(self, planner):
        """时间相关查询应检索 event_timeline。"""
        output, _ = planner.plan(
            query="韩立后来怎么样了",
            scope=Scope(),
            history=[],
        )

        assert "event_timeline" in output.retrieval_targets


class TestRetrievalIntent:
    """测试 retrieval_intent 映射。"""

    def test_causal_chain_has_causal_chain_intent(self, planner):
        """因果链查询应有 causal_chain intent。"""
        output, _ = planner.plan(
            query="韩立为什么参加测试",
            scope=Scope(),
            history=[],
        )

        assert output.retrieval_intent == "causal_chain"

    def test_character_analysis_has_alias_resolution_intent(self, planner):
        """人物分析查询应有 alias_resolution intent。"""
        output, _ = planner.plan(
            query="韩立是谁",
            scope=Scope(),
            history=[],
        )

        assert output.retrieval_intent == "alias_resolution"
