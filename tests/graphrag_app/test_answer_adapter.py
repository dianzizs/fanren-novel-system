"""Test answer adapter converts GraphRAG results to AskResponse."""

from novel_system.graphrag_app.answer_adapter import GraphRAGAnswerAdapter
from novel_system.graphrag_app.query_engine import GraphRAGQueryResult


def test_adapter_maps_result_fields_to_ask_response_contract():
    adapter = GraphRAGAnswerAdapter()
    result = GraphRAGQueryResult(
        response="韩立是主角，出身山边小村。",
        context_data={"debug": {"raw": "kept by query result"}},
        mode="local",
        matched_entities=["韩立", "墨大夫"],
        used_community_reports=["community-1"],
        used_text_units=["text-unit-1"],
    )

    response = adapter.to_ask_response(result)

    assert response.answer == result.response
    assert response.confidence == "high"
    assert response.planner.retrieval_targets == ["graphrag_local"]
    assert response.scope.chapters == []
    assert response.memory == {
        "search_mode": "local",
        "matched_entities": ["韩立", "墨大夫"],
    }
    assert [item.source for item in response.evidence] == [
        "entities",
        "entities",
        "community_reports",
    ]
    assert [item.title for item in response.evidence] == ["韩立", "墨大夫", "community-1"]
    assert response.trace is None


def test_adapter_fallback_evidence_and_medium_confidence_for_uncertain_answer():
    adapter = GraphRAGAnswerAdapter()
    result = GraphRAGQueryResult(
        response="无法确认。",
        context_data={},
        mode="global",
        matched_entities=[],
        used_community_reports=[],
        used_text_units=[],
    )

    response = adapter.to_ask_response(result)

    assert response.confidence == "medium"
    assert len(response.evidence) == 1
    assert response.evidence[0].target == "graphrag_global_search"
    assert response.evidence[0].source == "graphrag"
    assert response.evidence[0].quote == "无法确认。"


def test_adapter_produces_ask_response():
    adapter = GraphRAGAnswerAdapter()
    result = GraphRAGQueryResult(
        response="韩立是本书主角，出身山边小村。",
        context_data={},
        mode="local",
        matched_entities=["韩立"],
        used_community_reports=[],
        used_text_units=[],
    )

    response = adapter.to_ask_response(result)
    assert response.answer == result.response
    assert response.confidence in ("low", "medium", "high")
    assert len(response.evidence) > 0


def test_adapter_no_entities_has_evidence():
    adapter = GraphRAGAnswerAdapter()
    result = GraphRAGQueryResult(
        response="无法确认。",
        context_data={},
        mode="global",
        matched_entities=[],
        used_community_reports=[],
        used_text_units=[],
    )

    response = adapter.to_ask_response(result)
    assert response.answer == "无法确认。"
