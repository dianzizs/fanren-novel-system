from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .models import ConversationTurn, PlannerOutput, QueryIntent, Scope


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
    """基于规则的查询规划器。"""

    # 意图关键词模式（按优先级排序：更具体的意图先检查）
    INTENT_PATTERNS: dict[QueryIntent, list[str]] = {
        QueryIntent.SUMMARY: ["总结", "概括", "摘要", "简介"],
        QueryIntent.TEMPORAL: ["什么时候", "后来", "之后", "之前", "最终", "结局"],
        QueryIntent.CHARACTER_ANALYSIS: ["是谁", "性格", "外貌", "什么样的人", "人物卡"],
        QueryIntent.CAUSAL_CHAIN: ["为什么", "怎么", "原因", "结果", "怎么会", "怎么会这样"],
        QueryIntent.FACT_QUERY: ["是什么", "有哪些", "有没有", "是怎样的"],
    }

    # 意图到检索目标的映射
    INTENT_TARGETS: dict[QueryIntent, list[str]] = {
        QueryIntent.CAUSAL_CHAIN: ["event_timeline", "chapter_chunks"],
        QueryIntent.FACT_QUERY: ["chapter_chunks", "canon_memory"],
        QueryIntent.CHARACTER_ANALYSIS: ["character_card", "chapter_chunks"],
        QueryIntent.SUMMARY: ["chapter_summaries", "event_timeline"],
        QueryIntent.TEMPORAL: ["event_timeline", "recent_plot"],
        QueryIntent.GENERAL: ["chapter_chunks"],
    }

    def _detect_intent(self, query: str) -> QueryIntent:
        """检测查询意图（优先级最高）。

        Args:
            query: 用户查询

        Returns:
            检测到的意图类型
        """
        for intent, keywords in self.INTENT_PATTERNS.items():
            if any(kw in query for kw in keywords):
                return intent
        return QueryIntent.GENERAL

    def _get_retrieval_intent(self, intent: QueryIntent) -> str:
        """根据意图返回检索意图。"""
        mapping = {
            QueryIntent.CAUSAL_CHAIN: "causal_chain",
            QueryIntent.CHARACTER_ANALYSIS: "alias_resolution",
        }
        return mapping.get(intent, "scene_evidence")

    def _get_task_type(self, intent: QueryIntent, query: str) -> str:
        """根据意图返回任务类型。"""
        if intent == QueryIntent.SUMMARY:
            return "summary"
        if intent == QueryIntent.CHARACTER_ANALYSIS:
            return "analysis"
        return "qa"

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
                retrieval_intent="copyright_guard",
                constraints=["copyright_guard"],
                success_criteria=["refuse_long_quote", "offer_summary"],
            )
            return planner, memory

        if any(keyword in query for keyword in ("续写", "继续写", "仿写")):
            planner = PlannerOutput(
                task_type="continuation",
                retrieval_needed=True,
                retrieval_targets=["recent_plot", "character_card", "canon_memory", "style_samples"],
                retrieval_intent="scene_evidence",
                constraints=["stay_in_scope", "no_direct_long_quote", "consistency_check_before_output"],
                success_criteria=["character_consistent", "no_spoiler_beyond_scope", "style_close"],
            )
            return planner, memory

        if any(keyword in query for keyword in ("总结", "摘要", "概括")):
            planner = PlannerOutput(
                task_type="summary",
                retrieval_needed=True,
                retrieval_targets=["chapter_summaries", "event_timeline", "chapter_chunks"],
                retrieval_intent="scene_evidence",
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
                retrieval_intent="alias_resolution" if "人物" in query or "谁" in query else "scene_evidence",
                constraints=["structured_output", "grounded_answer"],
                success_criteria=["fields_complete", "no_spoiler_beyond_scope"],
            )
            return planner, memory

        if any(keyword in query for keyword in ("觉得", "性格", "分析", "怎么看")):
            planner = PlannerOutput(
                task_type="analysis",
                retrieval_needed=True,
                retrieval_targets=["character_card", "recent_plot"],
                retrieval_intent="alias_resolution",
                constraints=["brief_answer", "grounded_reason"],
                success_criteria=["clear_position", "evidence_backed"],
            )
            return planner, memory

        # === 意图优先路由（核心逻辑）===

        # 1. 检测意图（优先级最高）
        intent = self._detect_intent(query)

        # 2. 根据意图确定基础检索目标
        retrieval_targets = list(self.INTENT_TARGETS.get(intent, ["chapter_chunks"]))
        retrieval_intent = self._get_retrieval_intent(intent)

        # 3. 人名关键词作为辅助增强（不覆盖意图决策）
        person_keywords = ("韩立", "张铁", "墨大夫", "舞岩", "韩胖子", "三叔")
        if any(kw in query for kw in person_keywords) and intent != QueryIntent.CHARACTER_ANALYSIS:
            # 因果/事实问题：补充 character_card 用于上下文，但不优先
            if "character_card" not in retrieval_targets:
                retrieval_targets.append("character_card")

        # 4. 其他辅助逻辑
        if any(keyword in query for keyword in ("瓶子", "后来", "现在")):
            if "recent_plot" not in retrieval_targets:
                retrieval_targets.append("recent_plot")

        if multimodal:
            retrieval_targets = ["vision_parse", *retrieval_targets]

        planner = PlannerOutput(
            task_type=self._get_task_type(intent, query),
            retrieval_needed=True,
            retrieval_targets=list(dict.fromkeys(retrieval_targets)),
            retrieval_intent=retrieval_intent,
            constraints=["grounded_answer", "cite_evidence", "no_spoiler_beyond_scope"],
            success_criteria=["answer_correct", "answer_grounded"],
        )
        return planner, memory
