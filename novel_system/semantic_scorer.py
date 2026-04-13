"""
语义相似度计算模块

使用 sentence-transformers 计算文本嵌入向量，
支持预计算和在线计算两种模式。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

import numpy as np
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# 延迟加载模型，避免启动时加载
_model = None


def _get_model():
    """延迟加载 embedding 模型"""
    global _model
    if _model is None:
        try:
            from sentence_transformers import SentenceTransformer
            # 使用支持中文的多语言模型
            _model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
            logger.info("Loaded embedding model: paraphrase-multilingual-MiniLM-L12-v2")
        except ImportError:
            logger.warning("sentence-transformers not installed, semantic similarity will be disabled")
            _model = False  # 标记为不可用
    return _model if _model is not False else None


class EmbeddingCache(BaseModel):
    """嵌入向量缓存"""
    chunks: dict[str, list[float]] = {}  # chunk_id -> embedding
    model_name: str = ""
    dimension: int = 384


class SemanticScorer:
    """
    语义相似度评分器

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
        cache_path: Optional[Path] = None,
        use_precomputed: bool = True,
    ):
        """
        初始化评分器

        Args:
            cache_path: 预计算缓存文件路径
            use_precomputed: 是否使用预计算的向量
        """
        self.cache_path = cache_path
        self.use_precomputed = use_precomputed
        self._cache: Optional[EmbeddingCache] = None

        if use_precomputed and cache_path and cache_path.exists():
            self._load_cache()

    def _load_cache(self) -> None:
        """加载预计算的向量缓存"""
        if not self.cache_path:
            return

        try:
            with open(self.cache_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self._cache = EmbeddingCache(**data)
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

    def compute_embedding(self, text: str) -> Optional[np.ndarray]:
        """
        计算文本的嵌入向量

        Args:
            text: 输入文本

        Returns:
            嵌入向量 (384维) 或 None（如果模型不可用）
        """
        model = _get_model()
        if model is None:
            return None

        embedding = model.encode(text, convert_to_numpy=True)
        return embedding

    def compute_embeddings_batch(self, texts: list[str]) -> Optional[np.ndarray]:
        """
        批量计算嵌入向量

        Args:
            texts: 文本列表

        Returns:
            嵌入向量矩阵 (N, 384) 或 None
        """
        model = _get_model()
        if model is None:
            return None

        embeddings = model.encode(texts, convert_to_numpy=True, show_progress_bar=False)
        return embeddings

    def get_cached_embedding(self, chunk_id: str) -> Optional[np.ndarray]:
        """获取预计算的向量"""
        if not self._cache or chunk_id not in self._cache.chunks:
            return None
        return np.array(self._cache.chunks[chunk_id])

    def compute_similarity(
        self,
        query: str,
        text: str,
        chunk_id: Optional[str] = None,
    ) -> float:
        """
        计算查询与文本的语义相似度

        Args:
            query: 用户查询
            text: 目标文本
            chunk_id: 预计算向量ID（可选）

        Returns:
            相似度分数 (0-1)
        """
        # 1. 获取查询向量
        query_emb = self.compute_embedding(query)
        if query_emb is None:
            return 0.5  # 模型不可用时返回中等分数

        # 2. 获取目标向量
        if chunk_id and self.use_precomputed:
            text_emb = self.get_cached_embedding(chunk_id)
        else:
            text_emb = self.compute_embedding(text)

        if text_emb is None:
            return 0.5

        # 3. 计算余弦相似度
        similarity = self._cosine_similarity(query_emb, text_emb)

        # 4. 归一化到 0-1 范围（原始范围约 -1 到 1）
        normalized = (similarity + 1) / 2

        return float(normalized)

    def compute_similarity_with_hits(
        self,
        query: str,
        hits: list[Any],
    ) -> float:
        """
        计算查询与检索结果的综合相似度

        结合语义相似度和 BM25 分数

        Args:
            query: 用户查询
            hits: 检索结果列表

        Returns:
            综合相似度分数 (0-1)
        """
        if not hits:
            return 0.0

        model = _get_model()
        if model is None:
            # 模型不可用，回退到纯 BM25
            return self._compute_lexical_score(hits)

        # 计算查询向量
        query_emb = self.compute_embedding(query)
        if query_emb is None:
            return self._compute_lexical_score(hits)

        # 计算每个命中的综合分数
        scores = []
        for hit in hits:
            # 语义分数
            if hasattr(hit, 'chunk_id') and self.use_precomputed:
                text_emb = self.get_cached_embedding(hit.chunk_id)
            elif hasattr(hit, 'text'):
                text_emb = self.compute_embedding(hit.text)
            elif hasattr(hit, 'content'):
                text_emb = self.compute_embedding(hit.content)
            else:
                text_emb = None

            if text_emb is not None:
                semantic_score = (self._cosine_similarity(query_emb, text_emb) + 1) / 2
            else:
                semantic_score = 0.5

            # 词汇分数（BM25）
            lexical_score = self._normalize_bm25(getattr(hit, 'score', 0.5))

            # 综合分数
            combined = (
                self.SEMANTIC_WEIGHT * semantic_score +
                self.LEXICAL_WEIGHT * lexical_score
            )
            scores.append(combined)

        # 加权平均（前面的结果权重更高）
        if len(scores) == 1:
            return scores[0]

        weights = [0.5 ** i for i in range(len(scores))]
        total_weight = sum(weights)
        weighted_sum = sum(s * w for s, w in zip(scores, weights))

        return weighted_sum / total_weight

    def _cosine_similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        """计算余弦相似度"""
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(np.dot(a, b) / (norm_a * norm_b))

    def _normalize_bm25(self, score: float) -> float:
        """将 BM25 分数归一化到 0-1"""
        # BM25 分数通常在 0-30 范围
        return min(1.0, score / 15.0)

    def _compute_lexical_score(self, hits: list[Any]) -> float:
        """纯词汇匹配分数（回退方案）"""
        if not hits:
            return 0.0

        scores = []
        for hit in hits:
            score = getattr(hit, 'score', 0.0)
            scores.append(self._normalize_bm25(score))

        weights = [0.5 ** i for i in range(len(scores))]
        total_weight = sum(weights)
        return sum(s * w for s, w in zip(scores, weights)) / total_weight


def build_embedding_cache(
    chunks: list[dict[str, Any]],
    output_path: Path,
    text_field: str = "content",
    id_field: str = "id",
) -> None:
    """
    构建 chunk 向量缓存

    用于离线预计算，在索引阶段调用

    Args:
        chunks: chunk 列表，每个包含 id 和 text
        output_path: 输出文件路径
        text_field: 文本字段名
        id_field: ID字段名
    """
    model = _get_model()
    if model is None:
        logger.error("Cannot build cache: model not available")
        return

    texts = [chunk.get(text_field, "") for chunk in chunks]
    ids = [chunk.get(id_field, f"chunk_{i}") for i, chunk in enumerate(chunks)]

    # 批量计算
    logger.info(f"Computing embeddings for {len(texts)} chunks...")
    embeddings = model.encode(texts, convert_to_numpy=True, show_progress_bar=True)

    # 构建缓存
    cache = EmbeddingCache(
        chunks={id_: emb.tolist() for id_, emb in zip(ids, embeddings)},
        model_name="paraphrase-multilingual-MiniLM-L12-v2",
        dimension=embeddings.shape[1] if len(embeddings) > 0 else 384,
    )

    # 保存
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(cache.model_dump(), f, ensure_ascii=False)

    logger.info(f"Saved embedding cache to {output_path}")


# 全局单例
_scorer: Optional[SemanticScorer] = None


def get_scorer(cache_path: Optional[Path] = None) -> SemanticScorer:
    """获取全局评分器实例"""
    global _scorer
    if _scorer is None:
        _scorer = SemanticScorer(cache_path=cache_path)
    return _scorer
