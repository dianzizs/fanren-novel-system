"""Abstract base class for rerankers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class RerankResult:
    """重排序结果。"""
    document: dict[str, Any]
    original_score: float
    rerank_score: float
    final_score: float
    target: str
    rank: int = 0


class BaseReranker(ABC):
    """重排序器抽象基类。"""

    @abstractmethod
    def rerank(
        self,
        query: str,
        candidates: list[Any],
        top_k: int = 10,
        scope: Optional[list[int]] = None,
    ) -> list[RerankResult]:
        """
        重排序候选文档。

        Args:
            query: 用户查询
            candidates: 候选文档列表（list[RetrievalHit] 或类似结构）
            top_k: 返回数量
            scope: 章节范围

        Returns:
            重排序后的结果列表
        """
        pass

    @property
    @abstractmethod
    def is_ready(self) -> bool:
        """检查重排序器是否可用。"""
        pass
