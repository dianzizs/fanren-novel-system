"""Rule-based reranker for improving retrieval quality."""

from __future__ import annotations

import logging
import re
from typing import Any, Optional

from .base import BaseReranker, RerankResult

logger = logging.getLogger(__name__)


class RuleBasedReranker(BaseReranker):
    """
    基于规则的重排序器。

    考虑因素：
    1. 章节相关性（越接近 scope 中心章节权重越高）
    2. 实体匹配（查询中的人名/地名是否出现在文档中）
    3. 关键词密度
    4. 文档类型权重（character_card > chapter_chunks > 其他）
    """

    # 文档类型权重
    TARGET_WEIGHTS = {
        "character_card": 1.3,
        "chapter_chunks": 1.0,
        "event_timeline": 0.9,
        "chapter_summaries": 0.85,
        "world_rule": 0.8,
        "canon_memory": 0.75,
        "recent_plot": 0.7,
        "relationship_graph": 0.65,
        "style_samples": 0.6,
    }

    def __init__(
        self,
        target_weights: Optional[dict[str, float]] = None,
        chapter_weight: float = 0.2,
        entity_weight: float = 0.3,
        keyword_weight: float = 0.3,
        type_weight: float = 0.2,
    ):
        """
        初始化规则重排序器。

        Args:
            target_weights: 文档类型权重覆盖
            chapter_weight: 章节相关性权重
            entity_weight: 实体匹配权重
            keyword_weight: 关键词密度权重
            type_weight: 文档类型权重
        """
        self.target_weights = {**self.TARGET_WEIGHTS, **(target_weights or {})}
        self.chapter_weight = chapter_weight
        self.entity_weight = entity_weight
        self.keyword_weight = keyword_weight
        self.type_weight = type_weight

    @property
    def is_ready(self) -> bool:
        """规则重排序器始终可用。"""
        return True

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
            candidates: 候选文档列表
            top_k: 返回数量
            scope: 章节范围

        Returns:
            重排序后的结果列表
        """
        if not candidates:
            return []

        results = []
        for i, hit in enumerate(candidates):
            # 提取文档信息
            if hasattr(hit, "document"):
                doc = hit.document
                original_score = hit.score
                target = hit.target
            elif isinstance(hit, dict):
                doc = hit.get("document", hit)
                original_score = hit.get("score", 0.5)
                target = hit.get("target", "")
            else:
                continue

            # 计算各维度分数
            target_weight = self.target_weights.get(target, 1.0)
            entity_score = self._compute_entity_match(query, doc)
            keyword_score = self._compute_keyword_density(query, doc)
            chapter_score = self._compute_chapter_relevance(doc, scope)

            # 综合重排序分数
            rerank_score = (
                target_weight * self.type_weight +
                entity_score * self.entity_weight +
                keyword_score * self.keyword_weight +
                chapter_score * self.chapter_weight
            )

            # 最终分数 = 原始分数 * 0.4 + 重排序分数 * 0.6
            final_score = original_score * 0.4 + rerank_score * 0.6

            results.append(RerankResult(
                document=doc,
                original_score=original_score,
                rerank_score=rerank_score,
                final_score=final_score,
                target=target,
                rank=i,
            ))

        # 按最终分数排序
        results.sort(key=lambda x: x.final_score, reverse=True)
        for i, result in enumerate(results):
            result.rank = i + 1

        return results[:top_k]

    def _compute_entity_match(self, query: str, doc: dict[str, Any]) -> float:
        """
        计算实体匹配分数。

        检查查询中的人名/地名是否出现在文档中。
        """
        text = self._get_document_text(doc)
        if not text:
            return 0.0

        # 提取查询中的中文实体（2-4个字的词）
        entities = re.findall(r'[一-龥]{2,4}', query)

        if not entities:
            return 0.5  # 无实体时返回中等分数

        # 计算实体覆盖率
        matched = sum(1 for e in entities if e in text)
        return matched / len(entities)

    def _compute_keyword_density(self, query: str, doc: dict[str, Any]) -> float:
        """
        计算关键词密度分数。

        检查查询中的关键词在文档中的密度。
        """
        text = self._get_document_text(doc)
        if not text:
            return 0.0

        # 提取查询中的关键词（去除停用词）
        stopwords = {"这个", "那个", "就是", "不是", "没有", "可以", "知道", "一个", "什么", "怎么", "哪些", "为何", "为何是"}
        keywords = [kw for kw in re.findall(r'[一-龥]+', query) if kw not in stopwords and len(kw) >= 2]

        if not keywords:
            return 0.5

        # 计算关键词出现次数
        total_matches = sum(text.count(kw) for kw in keywords)

        # 归一化（假设每100字出现1次关键词为理想密度）
        text_len = len(text)
        if text_len == 0:
            return 0.0

        density = total_matches / (text_len / 100)
        return min(1.0, density)

    def _compute_chapter_relevance(
        self,
        doc: dict[str, Any],
        scope: Optional[list[int]],
    ) -> float:
        """
        计算章节相关性分数。

        越接近 scope 中心章节权重越高。
        """
        if not scope:
            return 0.5

        chapter = doc.get("chapter")
        if chapter is None:
            # 检查 active_range 或 chapter_span
            active_range = doc.get("active_range") or doc.get("chapter_span")
            if active_range and len(active_range) >= 2:
                # 使用范围的中心
                chapter = (active_range[0] + active_range[1]) / 2
            else:
                return 0.5

        min_chapter = min(scope)
        max_chapter = max(scope)
        center = (min_chapter + max_chapter) / 2
        radius = (max_chapter - min_chapter) / 2

        if radius == 0:
            return 1.0 if chapter == min_chapter else 0.5

        # 计算与中心的距离
        distance = abs(chapter - center)
        relevance = 1.0 - (distance / (radius * 2))
        return max(0.0, min(1.0, relevance))

    def _get_document_text(self, doc: dict[str, Any]) -> str:
        """获取文档文本。"""
        # 尝试多个可能的文本字段
        for field in ["text", "content", "quote", "description", "summary"]:
            value = doc.get(field)
            if value and isinstance(value, str):
                return value
        return ""
