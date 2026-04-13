from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .models import ConversationTurn, PlannerOutput, Scope


@dataclass
class MemoryState:
    """会话记忆状态"""
    preferred_length: str = "normal"
    wants_evidence: bool = False
    no_spoiler: bool = False
    scope_note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "preferred_length": self.preferred_length,
            "wants_evidence": self.wants_evidence,
            "no_spoiler": self.no_spoiler,
            "scope_note": self.scope_note,
        }


SHORT_PREFERENCE_RE = re.compile(r"(简短|短一点|精简|别太长)")
EVIDENCE_PREFERENCE_RE = re.compile(r"(带证据|给证据|附证据|附引用|带引用)")
NO_SPOILER_RE = re.compile(r"(不剧透|不要剧透|只看前\d+章|只基于前\d+章)")
FUTURE_RE = re.compile(r"(以后|后面|最终|最后|到底有什么用|秘密被完全揭开)")


# ── 查询重写 ──────────────────────────────────────────────
ALIAS_EXPANSIONS: dict[str, list[str]] = {
    "韩立": ["二愣子", "韩师弟"],
    "张铁": ["张师兄"],
    "墨大夫": ["墨老", "供奉"],
    "韩胖子": ["三叔", "韩立三叔"],
    "瓶子": ["小瓶", "神秘小瓶", "碧绿液体", "绿液", "掌天瓶"],
    "七玄门": ["七玄门", "门派", "内门", "外门"],
    "象甲功": ["象甲功", "铁甲功"],
    "口诀": ["无名口诀", "修身口诀", "长寿诀"],
    "炼骨崖": ["炼骨崖", "崖顶", "麻绳", "岩壁"],
    "神手谷": ["神手谷", "墨大夫住处"],
    "七绝堂": ["七绝堂", "堂口"],
    "供奉堂": ["供奉堂", "供奉"],
}

SCOPE_HINT_RE = re.compile(r"前\s*(\d+)\s*章")
CHAPTER_REF_RE = re.compile(r"第\s*(\d+)\s*章")
PRONOUN_RE = re.compile(r"他(的|们|是|在|有|把|被|给|又|也|还|就|却|都|已|将|曾|正|会|能|要|想|说|看|听|走|到|去|来|回)?")

RECENT_TOPIC_RES = [
    (re.compile(r"那个(东西|物件|瓶子)"), "神秘小瓶"),
    (re.compile(r"这(个)?功法"), "象甲功 无名口诀"),
    (re.compile(r"那个(人|老头)"), "墨大夫"),
]


@dataclass
class RewrittenQuery:
    original: str
    rewritten: str
    expansions: list[str]


class QueryRewriter:
    """规则化查询重写：扩展别名、补全指代、提取对话上下文"""

    def rewrite(
        self,
        query: str,
        scope: Scope,
        history: list[ConversationTurn],
    ) -> RewrittenQuery:
        parts: list[str] = [query]
        expansions: list[str] = []

        # 1) 别名扩展
        for key, aliases in ALIAS_EXPANSIONS.items():
            if key in query:
                expansions.append(f"{key}→{'、'.join(aliases)}")
                parts.append(" ".join(aliases))

        # 2) 指代消解（从最近对话历史中推断代词指向）
        recent_context = self._extract_recent_context(history)
        if recent_context:
            for pattern, replacement in RECENT_TOPIC_RES:
                if pattern.search(query):
                    expansions.append(f"指代消解→{replacement}")
                    parts.append(replacement)

        # 3) 章节范围补充到 query（帮助 TF-IDF 匹配含章节号的内容）
        chapter_refs = CHAPTER_REF_RE.findall(query)
        if chapter_refs:
            for ch in chapter_refs[:3]:
                parts.append(f"第{ch}章")

        # 4) 从对话历史中提取最近提到的人物/关键词
        if history:
            history_terms = self._extract_history_terms(history)
            if history_terms:
                expansions.append(f"历史上下文→{history_terms}")
                parts.append(history_terms)

        rewritten = " ".join(parts)
        return RewrittenQuery(
            original=query,
            rewritten=rewritten,
            expansions=expansions,
        )

    def _extract_recent_context(self, history: list[ConversationTurn]) -> str:
        """从最近2轮对话中提取关键名词"""
        terms: list[str] = []
        for turn in history[-4:]:
            if turn.role != "assistant":
                continue
            content = turn.content
            for key in ALIAS_EXPANSIONS:
                if key in content and key not in terms:
                    terms.append(key)
        return " ".join(terms[:5])

    def _extract_history_terms(self, history: list[ConversationTurn]) -> str:
        """从对话历史中提取用户关注的人物和实体"""
        terms: list[str] = []
        combined = " ".join(turn.content for turn in history if turn.role == "user")
        for key in ALIAS_EXPANSIONS:
            if key in combined and key not in terms:
                terms.append(key)
        return " ".join(terms[:5])


# ── 记忆与规划 ──────────────────────────────────────────────


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
