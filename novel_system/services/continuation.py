from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any

from ..models import (
    ContinueRequest,
    ContinuationResponse,
    ContinuationTrace,
    QueryRewriteTrace,
    RetrievalHitTrace,
    RetrievalTrace,
    Scope,
    ValidationResult,
)
from ..novel_heuristics import (
    NovelConfig,
    heuristic_continuation,
    get_continuation_template,
    get_safe_continuation_template,
)
from ..retrieval import RetrievalHit
from ..planner import MemoryState
from ..tracing import TraceLogger, trace_logger

logger = logging.getLogger(__name__)


class ContinuationServiceMixin:
    """续写相关的业务逻辑组合类。"""

    def continue_story(self, book_id: str, request: ContinueRequest) -> ContinuationResponse:
        """处理续写请求。"""
        trace_id = TraceLogger.generate_trace_id()
        start_time = time.perf_counter()

        self.ensure_indexed(book_id)
        book_index = self.repo.load(book_id)
        planner, memory = self.planner.plan(request.user_query, request.scope, request.conversation_history)
        if planner.task_type != "continuation":
            planner = PlannerOutput(
                task_type="continuation",
                retrieval_needed=True,
                retrieval_targets=["recent_plot", "character_card", "canon_memory", "style_samples"],
                constraints=["stay_in_scope", "consistency_check_before_output"],
                success_criteria=["character_consistent", "no_spoiler_beyond_scope"],
            )

        # === TRACING: 记录 query rewrite ===
        rewrite_start = time.perf_counter()
        rewritten = self.query_rewriter.rewrite(
            request.user_query,
            request.scope,
            request.conversation_history,
            book_id=book_id,
        )
        rewrite_duration = (time.perf_counter() - rewrite_start) * 1000

        query_rewrite_trace = QueryRewriteTrace(
            original=rewritten.original,
            rewritten=rewritten.rewritten,
            expansions=rewritten.expansions,
            duration_ms=round(rewrite_duration, 2),
        )

        # === TRACING: 记录 retrieval ===
        retrieval_start = time.perf_counter()
        hits = self._retrieve_with_rewrite(
            book_index,
            rewritten,
            planner,
            request.scope,
            request.top_k,
            request.test_harness.get("simulate"),
            book_id=book_id,
        )
        retrieval_duration = (time.perf_counter() - retrieval_start) * 1000

        answer, validation = self._execute_continuation_skill(
            book_id,
            query=request.user_query,
            hits=hits,
            memory=memory,
            scope=request.scope,
        )
        evidence = self._to_evidence_items(hits)
        evidence_spans = self._to_evidence_spans(hits)

        # === 验证层: Continuation Validator ===
        character_cards = book_index.corpora.get("character_card", [])
        world_rules = book_index.corpora.get("world_rule", [])
        style_samples = [doc.get("text", "") for doc in book_index.corpora.get("style_samples", [])[:5]]
        cont_validation = self.continuation_validator.validate(
            continuation=answer,
            character_cards=character_cards,
            world_rules=world_rules,
            style_samples=style_samples,
            scope=request.scope,
        )
        if cont_validation.character_issues:
            validation.setdefault("notes", []).extend(cont_validation.character_issues)
        if cont_validation.world_issues:
            validation.setdefault("notes", []).extend(cont_validation.world_issues)

        # === 验证层: Spoiler Guard ===
        total_chapters = int(book_index.manifest.get("chapter_count", 0))
        event_timeline = book_index.corpora.get("event_timeline", [])
        spoiler_risk = self.spoiler_guard.detect_spoiler(
            content=answer,
            scope=request.scope,
            total_chapters=total_chapters,
            event_timeline=event_timeline,
        )
        if spoiler_risk.level in ["medium", "high"]:
            answer = self.spoiler_guard.redact_content(answer, spoiler_risk)
            validation.setdefault("notes", []).append("检测到剧透风险，已处理")

        uncertainty = "medium" if validation.get("adjusted") else "low"
        if cont_validation.overall_score < 0.7:
            uncertainty = "medium"
        confidence = "high" if uncertainty == "low" else ("medium" if uncertainty == "medium" else "low")

        # === TRACING: 构建追踪数据 ===
        total_duration = (time.perf_counter() - start_time) * 1000

        retrieval_trace = RetrievalTrace(
            targets=planner.retrieval_targets,
            hits_count=len(hits),
            hits=[
                RetrievalHitTrace(
                    target=h.target,
                    document_id=h.document.get("id"),
                    chapter=h.document.get("chapter"),
                    score=round(h.score, 4),
                )
                for h in hits[:10]
            ],
            duration_ms=round(retrieval_duration, 2),
        )

        validation_result = ValidationResult(
            adjusted=validation.get("adjusted", False),
            notes=validation.get("notes", []),
            consistency_passed=validation.get("consistency_passed", True),
        )

        continuation_trace = ContinuationTrace(
            trace_id=trace_id,
            book_id=book_id,
            session_id=request.session_id,
            timestamp=datetime.now(),
            query_rewrite=query_rewrite_trace,
            planner=planner,
            retrieval=retrieval_trace,
            evidence_count=len(evidence),
            evidence_spans=evidence_spans,
            confidence=confidence,
            validation=validation_result,
            total_duration_ms=round(total_duration, 2),
            memory_state=memory.to_dict(),
        )

        trace_logger.log_continuation_trace(continuation_trace)

        self._remember_turns(request.session_id, request.user_query, answer)
        return ContinuationResponse(
            planner=planner,
            answer=answer,
            evidence=evidence,
            uncertainty=uncertainty,
            scope=request.scope,
            validation=validation,
            trace=continuation_trace if request.debug else None,
        )

    def _execute_continuation_skill(
        self,
        book_id: str,
        *,
        query: str,
        hits: list[RetrievalHit],
        memory: MemoryState,
        scope: Scope,
    ) -> tuple[str, dict[str, Any]]:
        book_index = self.repo.load(book_id)
        config = self._get_novel_config(book_id, book_index)
        scope_note = self._render_scope(scope)

        template = heuristic_continuation(query, config)
        if template:
            return template, {"adjusted": "超出" in template, "notes": [], "consistency_passed": True}

        adjusted = False
        notes: list[str] = []

        if self._check_forbidden_patterns(query, config):
            adjusted = True
            notes.append("用户要求超出当前设定，已自动弱化为符合前文范围的版本。")
            answer = self._fallback_safe_continuation(scope_note)
            return answer, {"adjusted": adjusted, "notes": notes, "consistency_passed": True}

        fallback = self._fallback_continuation(config)
        if not self.llm.enabled:
            return fallback, {"adjusted": False, "notes": notes, "consistency_passed": True}

        context = self._format_context(hits)
        style = self._format_style_samples(hits)

        character_prompt = config.get_character_prompt()

        messages = [
            {
                "role": "system",
                "content": (
                    "你是小说续写执行器。必须先保证人物动机、世界边界和时间范围一致，"
                    "再追求文风。不能提前揭示后文真相，不能突然跳战力，不能写现代网络语。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"当前范围：{scope_note}\n"
                    f"用户偏好：{self._render_memory(memory)}\n"
                    f"续写请求：{query}\n\n"
                    f"最近剧情与人物证据：\n{context}\n\n"
                    f"文风样本：\n{style}\n\n"
                    "请输出200到350字的中文续写。"
                    f"重点：{character_prompt}不要剧透后文。"
                    "如果用户要求本身越界，请先用一句话指出冲突，再给出符合当前设定的替代版本。"
                ),
            },
        ]
        try:
            result = self.llm.chat(messages, temperature=0.6, max_tokens=1200)
            self._record_token_usage(book_id, result.usage)
            answer = result.content
        except Exception:
            answer = fallback

        if self._check_forbidden_patterns(answer, config):
            adjusted = True
            notes.append("模型输出出现越界词，已回退到安全模板。")
            answer = self._fallback_safe_continuation(scope_note)
        return answer, {"adjusted": adjusted, "notes": notes, "consistency_passed": True}

    def _get_novel_config(self, book_id: str, book_index: Any = None) -> NovelConfig:
        from ..novel_heuristics import get_novel_config, extract_character_traits_from_index

        if book_id in self._novel_configs:
            return self._novel_configs[book_id]

        config = get_novel_config(book_id)

        if not config.character_traits and book_index:
            traits = extract_character_traits_from_index(book_index.corpora)
            if traits:
                config.character_traits = traits

        self._novel_configs[book_id] = config
        return config

    def _check_forbidden_patterns(self, text: str, config: NovelConfig) -> bool:
        for pattern in config.forbidden_patterns:
            if pattern in text:
                return True
        return False

    def _fallback_continuation(self, config: NovelConfig | None = None) -> str:
        return get_continuation_template(config)

    def _fallback_safe_continuation(self, scope_desc: str = "当前范围") -> str:
        return get_safe_continuation_template(scope_desc)

    def _format_context(self, hits: list[RetrievalHit]) -> str:
        if not hits:
            return "暂无足够证据。"
        blocks = []
        for index, hit in enumerate(hits[:8], start=1):
            quote = self._trim_quote(hit.document.get("text", ""))
            blocks.append(
                f"[{index}] target={hit.target} chapter={hit.document.get('chapter', 0)} "
                f"source={hit.document.get('source', '')}\n{quote}"
            )
        return "\n\n".join(blocks)

    def _format_style_samples(self, hits: list[RetrievalHit]) -> str:
        style_quotes = [
            self._trim_quote(hit.document.get("text", ""), 120)
            for hit in hits
            if hit.target == "style_samples"
        ]
        if not style_quotes:
            style_quotes = [self._trim_quote(hit.document.get("text", ""), 120) for hit in hits[:3]]
        return "\n".join(f"- {item}" for item in style_quotes[:4]) or "叙事朴素、克制。"
