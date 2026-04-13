"""
语义相似度计算模块

使用 EmbeddingProvider 计算文本嵌入向量，
支持预计算和在线计算两种模式。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

import numpy as np
from pydantic import BaseModel

from .embedding.base import ModelInfo
from .models import APIWarning

if TYPE_CHECKING:
    from .embedding.base import EmbeddingProvider

logger = logging.getLogger(__name__)


class EmbeddingCache(BaseModel):
    """嵌入向量缓存"""
    chunks: dict[str, list[float]] = {}  # chunk_id -> embedding
    # 元数据
    provider: str = ""
    device: str = ""
    model_name: str = ""
    model_revision: str = ""
    dimension: int = 512
    normalized: bool = True
    created_at: str = ""

    def is_compatible(self, model_info: ModelInfo) -> bool:
        """
        检查缓存是否与当前模型兼容

        Args:
            model_info: 当前模型信息

        Returns:
            True 如果兼容
        """
        return (
            self.provider == model_info.provider
            and self.model_name == model_info.model_name
            and self.dimension == model_info.dimension
        )


class SemanticScorer:
    """
    语义相似度评分器

    使用 EmbeddingProvider 计算语义相似度，
    结合 BM25 分数进行混合检索。

    支持两种模式：
    1. 预计算模式：在索引时计算所有 chunk 的 embedding，存储到文件
    2. 在线模式：查询时实时计算 embedding

    预计算模式延迟更低，适合生产环境。
    """

    # 相似度计算参数
    SEMANTIC_WEIGHT = 0.6  # 语义相似度权重
    LEXICAL_WEIGHT = 0.4   # 词汇匹配权重

    def __init__(
        self,
        embedding_provider: "EmbeddingProvider",
        cache_path: Optional[Path] = None,
    ):
        """
        初始化评分器

        Args:
            embedding_provider: Embedding Provider 实例
            cache_path: 预计算缓存文件路径
        """
        self.embedding_provider = embedding_provider
        self.cache_path = cache_path
        self._cache: Optional[EmbeddingCache] = None

        if cache_path and cache_path.exists():
            self._load_cache()

    def _load_cache(self) -> None:
        """加载预计算的向量缓存"""
        if not self.cache_path:
            return

        try:
            with open(self.cache_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self._cache = EmbeddingCache(**data)

            # 检查缓存兼容性
            model_info = self.embedding_provider.get_model_info()
            if not self._cache.is_compatible(model_info):
                logger.warning(
                    f"Embedding cache incompatible. "
                    f"Cache: provider={self._cache.provider}, model={self._cache.model_name}, dim={self._cache.dimension}. "
                    f"Current: provider={model_info.provider}, model={model_info.model_name}, dim={model_info.dimension}. "
                    f"Cache will be rebuilt."
                )
                self._cache = None
            else:
                logger.info(f"Loaded embedding cache: {len(self._cache.chunks)} chunks")
        except Exception as e:
            logger.warning(f"Failed to load embedding cache: {e}")
            self._cache = None

    def save_cache(self, path: Optional[Path] = None) -> None:
        """保存向量缓存"""
        save_path = path or self.cache_path
        if not save_path or not self._cache:
            return

        with open(save_path, 'w', encoding='utf-8') as f:
            json.dump(self._cache.model_dump(), f, ensure_ascii=False, indent=2)
        logger.info(f"Saved embedding cache to {save_path}")

    def compute_embedding(self, text: str) -> list[float]:
        """
        计算文本的嵌入向量

        Args:
            text: 输入文本

        Returns:
            嵌入向量列表
        """
        return self.embedding_provider.embed([text])[0]

    def compute_embeddings_batch(self, texts: list[str]) -> list[list[float]]:
        """
        批量计算嵌入向量

        Args:
            texts: 文本列表

        Returns:
            嵌入向量列表
        """
        return self.embedding_provider.embed(texts)

    def get_cached_embedding(self, chunk_id: str) -> Optional[list[float]]:
        """获取预计算的向量"""
        if not self._cache or chunk_id not in self._cache.chunks:
            return None
        return self._cache.chunks[chunk_id]

    def compute_similarity_with_hits(
        self,
        query: str,
        hits: list[Any],
    ) -> tuple[float, Optional[APIWarning]]:
        """
        计算查询与检索结果的综合相似度

        结合语义相似度和 BM25 分数

        Args:
            query: 用户查询
            hits: 检索结果列表

        Returns:
            tuple: (综合相似度分数, 告警或 None)
        """
        if not hits:
            return 0.0, None

        try:
            # 计算 query embedding
            query_emb = self.compute_embedding(query)

            scores = []
            for hit in hits:
                # 获取文本 embedding
                chunk_id = getattr(hit, 'chunk_id', None)
                if chunk_id and self._cache:
                    text_emb = self.get_cached_embedding(chunk_id)
                else:
                    text = getattr(hit, 'text', None) or getattr(hit, 'content', '')
                    text_emb = self.compute_embedding(text) if text else None

                if text_emb:
                    semantic_score = self._cosine_similarity(query_emb, text_emb)
                    semantic_score = (semantic_score + 1) / 2  # 归一化到 0-1
                else:
                    semantic_score = 0.5

                # 词汇分数（BM25）
                lexical_score = self._normalize_bm25(getattr(hit, 'score', 0.5))

                # 混合分数
                combined = (
                    self.SEMANTIC_WEIGHT * semantic_score +
                    self.LEXICAL_WEIGHT * lexical_score
                )
                scores.append(combined)

            # 加权平均
            return self._weighted_average(scores), None

        except RuntimeError as e:
            logger.error(f"Embedding failed: {e}")
            warning = APIWarning(
                type="embedding_fallback",
                message="语义相似度计算暂时不可用，已使用基础匹配算法",
                severity="warning",
            )
            return self._compute_lexical_score(hits), warning

        except Exception as e:
            logger.error(f"Unexpected error in semantic scoring: {e}")
            warning = APIWarning(
                type="api_error",
                message="检索服务遇到问题，结果可能不够精确",
                severity="error",
            )
            return self._compute_lexical_score(hits), warning

    def _cosine_similarity(self, a: list[float], b: list[float]) -> float:
        """计算余弦相似度"""
        a_arr, b_arr = np.array(a), np.array(b)
        norm_a, norm_b = np.linalg.norm(a_arr), np.linalg.norm(b_arr)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(np.dot(a_arr, b_arr) / (norm_a * norm_b))

    def _normalize_bm25(self, score: float) -> float:
        """将 BM25 分数归一化到 0-1"""
        return min(1.0, score / 15.0)

    def _compute_lexical_score(self, hits: list[Any]) -> float:
        """纯词汇匹配分数（降级方案）"""
        scores = [self._normalize_bm25(getattr(h, 'score', 0.0)) for h in hits]
        return self._weighted_average(scores)

    def _weighted_average(self, scores: list[float]) -> float:
        """指数衰减加权平均"""
        if not scores:
            return 0.0
        if len(scores) == 1:
            return scores[0]
        weights = [0.5 ** i for i in range(len(scores))]
        return sum(s * w for s, w in zip(scores, weights)) / sum(weights)


def build_embedding_cache(
    chunks: list[dict[str, Any]],
    output_path: Path,
    embedding_provider: "EmbeddingProvider",
    text_field: str = "content",
    id_field: str = "id",
) -> None:
    """
    构建 chunk 向量缓存

    用于离线预计算，在索引阶段调用

    Args:
        chunks: chunk 列表，每个包含 id 和 text
        output_path: 输出文件路径
        embedding_provider: Embedding Provider 实例
        text_field: 文本字段名
        id_field: ID字段名
    """
    texts = [chunk.get(text_field, "") for chunk in chunks]
    ids = [chunk.get(id_field, f"chunk_{i}") for i, chunk in enumerate(chunks)]

    # 批量计算
    logger.info(f"Computing embeddings for {len(texts)} chunks...")
    embeddings = embedding_provider.embed(texts)
    logger.info(f"Processed {len(texts)} chunks")

    # 获取模型信息
    model_info = embedding_provider.get_model_info()

    # 构建缓存
    cache = EmbeddingCache(
        chunks={id_: emb for id_, emb in zip(ids, embeddings)},
        provider=model_info.provider,
        device=model_info.device,
        model_name=model_info.model_name,
        dimension=model_info.dimension,
        normalized=model_info.normalized,
        created_at=datetime.now().isoformat(),
    )

    # 保存
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(cache.model_dump(), f, ensure_ascii=False, indent=2)

    logger.info(f"Saved embedding cache to {output_path}")


# 全局单例
_scorer: Optional[SemanticScorer] = None


def get_scorer(
    embedding_provider: Optional["EmbeddingProvider"] = None,
    cache_path: Optional[Path] = None,
) -> Optional[SemanticScorer]:
    """
    获取全局评分器实例

    Args:
        embedding_provider: Embedding Provider 实例（首次调用时需要）
        cache_path: 缓存文件路径

    Returns:
        SemanticScorer 实例或 None（如果 embedding_provider 未提供）
    """
    global _scorer
    if _scorer is None and embedding_provider is not None:
        _scorer = SemanticScorer(embedding_provider=embedding_provider, cache_path=cache_path)
    return _scorer
