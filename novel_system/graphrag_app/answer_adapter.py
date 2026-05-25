"""Adapt GraphRAG query results to existing AskResponse format."""

from __future__ import annotations

from ..models import (
    AskResponse,
    EvidenceItem,
    PlannerOutput,
    Scope,
)
from .query_engine import GraphRAGQueryResult


class GraphRAGAnswerAdapter:
    """Convert GraphRAGQueryResult -> AskResponse for API compatibility."""

    def to_ask_response(
        self,
        result: GraphRAGQueryResult,
        planner: PlannerOutput | None = None,
        scope: Scope | None = None,
        trace: dict | None = None,
    ) -> AskResponse:
        planner = planner or PlannerOutput(
            task_type="qa",
            retrieval_needed=True,
            retrieval_targets=["graphrag_" + result.mode],
        )
        scope = scope or Scope()

        evidence = self._extract_evidence(result)

        confidence = "high" if result.response and "无法" not in result.response else "medium"

        return AskResponse(
            planner=planner,
            answer=result.response,
            evidence=evidence,
            confidence=confidence,
            scope=scope,
            memory={
                "search_mode": result.mode,
                "matched_entities": result.matched_entities[:10],
            },
        )

    def _extract_evidence(self, result: GraphRAGQueryResult) -> list[EvidenceItem]:
        items: list[EvidenceItem] = []
        for name in result.matched_entities[:5]:
            items.append(EvidenceItem(
                target="graphrag_entity",
                chapter=0,
                title=name,
                score=1.0,
                quote="",
                source="entities",
            ))
        for report_id in result.used_community_reports[:3]:
            items.append(EvidenceItem(
                target="graphrag_community_report",
                chapter=0,
                title=report_id,
                score=0.9,
                quote="",
                source="community_reports",
            ))
        if not items:
            items.append(EvidenceItem(
                target=f"graphrag_{result.mode}_search",
                chapter=0,
                title="GraphRAG 搜索结果",
                score=1.0,
                quote=result.response[:120],
                source="graphrag",
            ))
        return items
