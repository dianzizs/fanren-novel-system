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
            scope=Scope(),
        )
        assert response.confidence == "high"
