from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .models import ConversationTurn, PlannerOutput, Scope


SHORT_PREFERENCE_RE = re.compile(r"(简短|短一点|精简|别太长)")
EVIDENCE_PREFERENCE_RE = re.compile(r"(带证据|给证据|附证据|附引用|带引用)")
NO_SPOILER_RE = re.compile(r"(不剧透|不要剧透|只看前\d+章|只基于前\d+章)")
FUTURE_RE = re.compile(r"(以后|后面|最终|最后|到底有什么用|秘密被完全揭开)")


@dataclass(slots=True)
class MemoryState:
    preferred_length: str = "normal"
    wants_evidence: bool = True
    no_spoiler: bool = True
    scope_note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "preferred_length": self.preferred_length,
            "wants_evidence": self.wants_evidence,
            "no_spoiler": self.no_spoiler,
            "scope_note": self.scope_note,
        }


class RuleBasedPlanner:
    def infer_memory(self, history: list[ConversationTurn], scope: Scope) -> MemoryState:
        state = MemoryState()
        for turn in history:
            if turn.role != "user":
                continue
            content = turn.content
            if SHORT_PREFERENCE_RE.search(content):
                state.preferred_length = "short"
            if EVIDENCE_PREFERENCE_RE.search(content):
                state.wants_evidence = True
            if NO_SPOILER_RE.search(content):
                state.no_spoiler = True
                state.scope_note = content
        if scope.chapters:
            state.scope_note = f"仅基于第{min(scope.chapters)}章到第{max(scope.chapters)}章。"
        return state

    def plan(
        self,
        query: str,
        scope: Scope,
        history: list[ConversationTurn],
        *,
        multimodal: bool = False,
    ) -> tuple[PlannerOutput, MemoryState]:
        memory = self.infer_memory(history, scope)
        lowered = query.lower()
        if any(keyword in query for keyword in ("完整输出", "全文", "原文")):
            planner = PlannerOutput(
                task_type="copyright_request",
                retrieval_needed=False,
                retrieval_targets=[],
                constraints=["copyright_guard"],
                success_criteria=["refuse_long_quote", "offer_summary"],
            )
            return planner, memory

        if any(keyword in query for keyword in ("续写", "继续写", "仿写")):
            planner = PlannerOutput(
                task_type="continuation",
                retrieval_needed=True,
                retrieval_targets=["recent_plot", "character_card", "canon_memory", "style_samples"],
                constraints=["stay_in_scope", "no_direct_long_quote", "consistency_check_before_output"],
                success_criteria=["character_consistent", "no_spoiler_beyond_scope", "style_close"],
            )
            return planner, memory

        if any(keyword in query for keyword in ("总结", "摘要", "概括")):
            planner = PlannerOutput(
                task_type="summary",
                retrieval_needed=True,
                retrieval_targets=["chapter_summaries", "event_timeline", "chapter_chunks"],
                constraints=["ordered_summary", "grounded_answer"],
                success_criteria=["key_events_covered", "no_spoiler_beyond_scope"],
            )
            return planner, memory

        if any(keyword in query for keyword in ("人物卡", "时间线", "整理", "抽一张", "关系", "势力", "抽取")):
            retrieval_targets = ["character_card", "chapter_chunks"]
            if "时间线" in query:
                retrieval_targets = ["event_timeline", "chapter_chunks"]
            elif "关系" in query or "势力" in query:
                retrieval_targets = ["character_card", "relationship_graph", "world_rule", "chapter_summaries"]
            planner = PlannerOutput(
                task_type="extract",
                retrieval_needed=True,
                retrieval_targets=retrieval_targets,
                constraints=["structured_output", "grounded_answer"],
                success_criteria=["fields_complete", "no_spoiler_beyond_scope"],
            )
            return planner, memory

        if any(keyword in query for keyword in ("觉得", "性格", "分析", "怎么看")):
            planner = PlannerOutput(
                task_type="analysis",
                retrieval_needed=True,
                retrieval_targets=["character_card", "recent_plot"],
                constraints=["brief_answer", "grounded_reason"],
                success_criteria=["clear_position", "evidence_backed"],
            )
            return planner, memory

        if FUTURE_RE.search(query):
            planner = PlannerOutput(
                task_type="qa",
                retrieval_needed=True,
                retrieval_targets=["recent_plot", "canon_memory", "chapter_chunks"],
                constraints=["grounded_answer", "cite_evidence", "no_spoiler_beyond_scope"],
                success_criteria=["answer_correct", "scope_guard"],
            )
            return planner, memory

        retrieval_targets = ["chapter_chunks"]
        if any(keyword in query for keyword in ("为什么", "结果", "怎么", "原因")):
            retrieval_targets = ["event_timeline", "chapter_chunks"]
        if any(keyword in query for keyword in ("人物", "谁", "关系", "韩立", "张铁", "墨大夫", "舞岩", "韩胖子", "三叔")):
            retrieval_targets = ["character_card", *retrieval_targets]
        if any(keyword in query for keyword in ("瓶子", "后来", "现在")):
            retrieval_targets = ["recent_plot", *retrieval_targets]
        if multimodal:
            retrieval_targets = ["vision_parse", *retrieval_targets]
        planner = PlannerOutput(
            task_type="qa",
            retrieval_needed=True,
            retrieval_targets=list(dict.fromkeys(retrieval_targets)),
            constraints=["grounded_answer", "cite_evidence", "no_spoiler_beyond_scope"],
            success_criteria=["answer_correct", "answer_grounded"],
        )
        return planner, memory
