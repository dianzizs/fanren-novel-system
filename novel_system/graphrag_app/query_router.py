"""Route queries to appropriate GraphRAG search mode."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

LOCAL_KEYWORDS = [
    "人物", "角色", "是谁", "什么关系", "长得", "外貌", "性格",
    "功法", "法宝", "丹药", "武器", "技能", "法术",
    "地点", "在哪里", "洞府", "门派", "境界", "修为",
    "关系", "认识", "交手", "战斗",
]

GLOBAL_KEYWORDS = [
    "主题", "主线", "整体", "全书", "格局", "总结", "概述",
    "势力格局", "人物群像", "世界观", "修炼体系",
    "宏观", "全局", "综合", "梳理",
]

DRIFT_KEYWORDS = [
    "为什么", "原因", "动机", "目的", "因果",
    "怎么会", "如何导致", "背后", "深层",
    "转变", "变化", "发展",
]


class GraphRAGQueryRouter:
    """Route user queries to local/global/drift/basic search modes."""

    def route(self, query: str, requested_mode: str | None = None) -> str:
        if requested_mode and requested_mode != "auto":
            return requested_mode

        local_score = sum(1 for kw in LOCAL_KEYWORDS if kw in query)
        global_score = sum(1 for kw in GLOBAL_KEYWORDS if kw in query)
        drift_score = sum(1 for kw in DRIFT_KEYWORDS if kw in query)

        if drift_score >= global_score and drift_score >= local_score and drift_score > 0:
            return "drift"
        if global_score > local_score and global_score > 0:
            return "global"
        if local_score > 0:
            return "local"

        return "local"
