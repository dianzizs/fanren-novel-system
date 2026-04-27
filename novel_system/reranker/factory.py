"""Factory function for creating rerankers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from .base import BaseReranker
from .rule_based import RuleBasedReranker

if TYPE_CHECKING:
    from ..config import AppConfig


def create_reranker(
    config: Optional["AppConfig"] = None,
    reranker_type: Optional[str] = None,
) -> Optional[BaseReranker]:
    """
    创建重排序器。

    Args:
        config: 应用配置
        reranker_type: 重排序器类型覆盖

    Returns:
        重排序器实例，如果禁用则返回 None
    """
    if config is None:
        return RuleBasedReranker()

    # 从配置获取重排序器类型
    rtype = reranker_type or getattr(config, "reranker_type", "rule_based")

    if rtype == "none" or not getattr(config, "rerank_enabled", True):
        return None
    elif rtype == "rule_based":
        return RuleBasedReranker(
            target_weights=getattr(config, "reranker_target_weights", None),
        )
    else:
        logger = __import__("logging").getLogger(__name__)
        logger.warning(f"Unknown reranker type: {rtype}, falling back to rule_based")
        return RuleBasedReranker()
