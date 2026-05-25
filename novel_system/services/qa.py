"""QA service backed by GraphRAG query engine."""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any

from ..models import (
    APIWarning,
    AskRequest,
    AskResponse,
    AskTrace,
    EvidenceItem,
    EvidenceSpan,
    PlannerOutput,
    RetrievalHitTrace,
    RetrievalTrace,
)
from ..tracing import TraceLogger, trace_logger

logger = logging.getLogger(__name__)


class QAServiceMixin:
    """GraphRAG-based QA mixin."""

    async def ask(self, book_id: str, request: AskRequest) -> AskResponse:
        trace_id = TraceLogger.generate_trace_id()
        start_time = time.perf_counter()

        self.ensure_indexed(book_id)

        mode = self.graphrag_query_router.route(
            request.user_query,
            requested_mode=request.search_mode if request.search_mode != "auto" else None,
        )

        result = await self.graphrag_query_engine.search(
            book_id=book_id,
            query=request.user_query,
            mode=mode,
            conversation_history=[t.model_dump() for t in request.conversation_history],
        )

        planner = PlannerOutput(
            task_type="qa",
            retrieval_needed=True,
            retrieval_targets=["graphrag_" + result.mode],
        )

        response = self.graphrag_answer_adapter.to_ask_response(result, planner=planner, scope=request.scope)

        if request.debug:
            total_duration = (time.perf_counter() - start_time) * 1000
            ask_trace = AskTrace(
                trace_id=trace_id,
                book_id=book_id,
                session_id=request.session_id,
                timestamp=datetime.now(),
                query_rewrite=None,
                planner=planner,
                retrieval=RetrievalTrace(
                    targets=["graphrag_" + result.mode],
                    hits_count=len(result.matched_entities),
                    hits=[
                        RetrievalHitTrace(target="graphrag_entity", document_id=name, score=1.0)
                        for name in result.matched_entities[:10]
                    ],
                    duration_ms=total_duration,
                ),
                evidence_count=len(response.evidence),
                evidence_spans=[],
                confidence=response.confidence,
                total_duration_ms=round(total_duration, 2),
                memory_state=response.memory,
            )
            response.trace = ask_trace
            trace_logger.log_ask_trace(ask_trace)

        self._remember_turns(request.session_id, request.user_query, response.answer)
        return response

    def _to_evidence_items(self, hits: list[Any]) -> list[EvidenceItem]:
        items = []
        for hit in hits[:5]:
            if hasattr(hit, 'document'):
                doc = hit.document
                items.append(EvidenceItem(
                    target=getattr(hit, 'target', 'unknown'),
                    chapter=int(doc.get("chapter", 0)),
                    title=doc.get("title", ""),
                    score=round(getattr(hit, 'score', 0.0), 4),
                    quote=self._trim_quote(doc.get("text", ""), 120),
                    source=doc.get("source", ""),
                ))
        return items

    def _to_evidence_spans(self, hits: list[Any]) -> list[EvidenceSpan]:
        spans = []
        for hit in hits[:5]:
            if hasattr(hit, 'document'):
                doc = hit.document
                spans.append(EvidenceSpan(
                    document_id=doc.get("id", ""),
                    chapter=doc.get("chapter"),
                    text_snippet=self._trim_quote(doc.get("text", ""), 120),
                    relevance_score=round(getattr(hit, 'score', 0.0), 4),
                    source_type=getattr(hit, 'target', 'unknown'),
                ))
        return spans
