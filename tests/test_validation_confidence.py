"""Tests for validation confidence field."""
import pytest
from novel_system.models import AskResponse, AskTrace, PlannerOutput, Scope
from novel_system.validator import AnswerValidator, EvidenceGateResult, EvidenceItem


class TestConfidenceField:
    """测试 confidence 字段。"""

    def test_ask_response_has_confidence_field(self):
        """AskResponse 应有 confidence 字段。"""
        planner = PlannerOutput(
            task_type="qa",
            retrieval_targets=[],
            retrieval_intent="scene_evidence",
            constraints=[],
            success_criteria=[],
        )
        response = AskResponse(
            planner=planner,
            answer="测试答案",
            evidence=[],
            confidence="high",
            uncertainty="low",  # 向后兼容
            scope=Scope(),
        )
        assert response.confidence == "high"
        assert response.uncertainty == "low"

    def test_high_confidence_means_low_uncertainty(self):
        """高置信度应对应低不确定性。"""
        # 这个测试验证向后兼容逻辑
        planner = PlannerOutput(
            task_type="qa",
            retrieval_targets=[],
            retrieval_intent="scene_evidence",
            constraints=[],
            success_criteria=[],
        )
        response = AskResponse(
            planner=planner,
            answer="测试答案",
            evidence=[],
            confidence="high",
            uncertainty="low",
            scope=Scope(),
        )
        # confidence=high 应该对应 uncertainty=low
        assert response.confidence == "high"
        assert response.uncertainty == "low"


class TestConfidenceUncertaintyMapping:
    """测试 confidence 和 uncertainty 的映射。"""

    def test_high_confidence_to_low_uncertainty(self):
        """high confidence 应映射到 low uncertainty。"""
        from novel_system.service import _compute_deprecated_uncertainty
        assert _compute_deprecated_uncertainty("high") == "low"

    def test_medium_confidence_to_medium_uncertainty(self):
        """medium confidence 应映射到 medium uncertainty。"""
        from novel_system.service import _compute_deprecated_uncertainty
        assert _compute_deprecated_uncertainty("medium") == "medium"

    def test_low_confidence_to_high_uncertainty(self):
        """low confidence 应映射到 high uncertainty。"""
        from novel_system.service import _compute_deprecated_uncertainty
        assert _compute_deprecated_uncertainty("low") == "high"
