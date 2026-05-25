"""Continuation service - downgraded during GraphRAG migration.

Phase 1: Returns downgrade notice while GraphRAG stabilizes.
Phase 2: Will use Basic Search for style samples + Local Search for character context.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any

from ..models import (
    ContinueRequest,
    ContinuationResponse,
    ContinuationTrace,
    PlannerOutput,
    RetrievalHitTrace,
    RetrievalTrace,
    ValidationResult,
)
from ..planner import MemoryState
from ..tracing import TraceLogger, trace_logger

logger = logging.getLogger(__name__)


class ContinuationServiceMixin:
    """Continuation mixin - downgraded during GraphRAG migration."""

    async def continue_story(self, book_id: str, request: ContinueRequest) -> ContinuationResponse:
        trace_id = TraceLogger.generate_trace_id()
        start_time = time.perf_counter()

        planner = PlannerOutput(
            task_type="continuation",
            retrieval_needed=True,
            retrieval_targets=["graphrag_basic"],
            constraints=["consistency_check_before_output"],
            success_criteria=["character_consistent"],
        )

        answer = (
            "续写功能正在进行 GraphRAG 迁移升级。"
            "当前您可以使用问答功能（支持 local/global/drift/basic 四种搜索模式）"
            "来查询人物、事件、设定等信息。续写将在后续版本恢复。"
        )

        total_duration = (time.perf_counter() - start_time) * 1000

        if request.debug:
            continuation_trace = ContinuationTrace(
                trace_id=trace_id,
                book_id=book_id,
                session_id=request.session_id,
                timestamp=datetime.now(),
                query_rewrite=None,
                planner=planner,
                retrieval=RetrievalTrace(
                    targets=["graphrag_basic"],
                    hits_count=0,
                    hits=[],
                    duration_ms=total_duration,
                ),
                evidence_count=0,
                evidence_spans=[],
                confidence="medium",
                validation=ValidationResult(adjusted=False, notes=["续写功能迁移中"], consistency_passed=True),
                total_duration_ms=round(total_duration, 2),
                memory_state={},
            )
            trace_logger.log_continuation_trace(continuation_trace)

        return ContinuationResponse(
            planner=planner,
            answer=answer,
            evidence=[],
            scope=request.scope,
            trace=continuation_trace if request.debug else None,
        )
