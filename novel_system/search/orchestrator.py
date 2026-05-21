"""Search orchestrator for multi-target retrieval."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, TYPE_CHECKING

import jieba
import jieba.posseg as pseg

from .profiles import TARGET_PROFILES

if TYPE_CHECKING:
    from ..vector_store.base import BaseVectorStore

logger = logging.getLogger(__name__)


def reciprocal_rank_fusion(
    candidates: list[dict[str, Any]],
    k: int = 60,
) -> list[dict[str, Any]]:
    """使用 RRF 算法合并多通道检索结果。

    RRF 公式: score = sum(1 / (k + rank)) for each channel

    Args:
        candidates: 候选文档列表，每个包含 channel 字段标识来源通道
        k: RRF 参数，默认 60（主流默认值）

    Returns:
        合并后的候选列表，按 RRF 分数排序
    """
    # 按 (target, document_id) 分组，收集各通道的排名
    doc_scores: dict[tuple[str, str], dict[str, Any]] = {}
    doc_ranks: dict[tuple[str, str], dict[str, int]] = {}

    # 按通道分组计算排名
    channels: dict[str, list[dict[str, Any]]] = {}
    for item in candidates:
        channel = item.get("channel", "default")
        if channel not in channels:
            channels[channel] = []
        channels[channel].append(item)

    # 计算每个通道内的排名
    for channel, items in channels.items():
        # 按原始分数排序
        sorted_items = sorted(items, key=lambda x: x.get("score", 0), reverse=True)
        for rank, item in enumerate(sorted_items, start=1):
            key = (item["target"], item["document_id"])
            if key not in doc_scores:
                # 创建副本避免修改原始对象
                doc_scores[key] = {**item}
                doc_ranks[key] = {}
            doc_ranks[key][channel] = rank

    # 计算 RRF 分数
    results: list[dict[str, Any]] = []
    for key, item in doc_scores.items():
        rrf_score = sum(1.0 / (k + rank) for rank in doc_ranks[key].values())
        item["score"] = rrf_score
        item["rrf_details"] = {"channels": doc_ranks[key], "k": k}
        results.append(item)

    # 按 RRF 分数排序
    results.sort(key=lambda x: x["score"], reverse=True)
    return results


@dataclass
class Hit:
    """A search hit."""
    target: str
    document: dict[str, Any]
    score: float


class SearchOrchestrator:
    """Orchestrates multi-target retrieval with alias resolution.

    Priority:
    1. Exact alias match (for character_card)
    2. Sparse text match (TF-IDF like)
    """

    def __init__(self, overfetch_factor: int = 10) -> None:
        """Initialize the search orchestrator.

        Args:
            overfetch_factor: Multiplier for dense search over-fetch when
                chapter_scope is applied. Defaults to 10.
        """
        self._overfetch_factor = overfetch_factor

    def retrieve(
        self,
        *,
        book_index: Any,
        query: str,
        targets: list[str],
        chapter_scope: list[int],
        top_k: int,
        query_embedding: list[float] | None = None,
        character_names: set[str] | None = None,
    ) -> list[Hit]:
        """Retrieve candidates from multiple targets.

        Args:
            book_index: Book index with corpora dict.
            query: User query string.
            targets: List of target names to search.
            chapter_scope: Chapter range for filtering.
            top_k: Maximum results to return.
            query_embedding: Optional query vector for dense search.
            character_names: Optional set of known character names for
                keyword weighting. Loaded from graph profile when available.

        Returns:
            List of Hit objects sorted by score.
        """
        hits: list[dict[str, Any]] = []
        for target in targets:
            all_docs = list(book_index.corpora.get(target, []))
            doc_pairs = list(enumerate(all_docs))
            # Filter by chapter scope
            if chapter_scope:
                doc_pairs = [
                    (index, doc)
                    for index, doc in doc_pairs
                    if self._in_scope(doc, chapter_scope)
                ]
            docs = [doc for _, doc in doc_pairs]
            doc_indices = [index for index, _ in doc_pairs]

            # 特殊处理：character_card 精确别名匹配
            if target == "character_card":
                alias_hits = self._exact_character_hits(query, docs)
                for hit in alias_hits:
                    hit["channel"] = "alias"
                hits.extend(alias_hits)

            # 向量检索（如果提供了 query_embedding）
            if query_embedding is not None:
                vector_store = book_index.vector_stores.get(target)
                if vector_store is not None:
                    dense_hits = self._dense_search(
                        query_vector=query_embedding,
                        vector_store=vector_store,
                        target=target,
                        top_k=top_k,
                        chapter_scope=chapter_scope,
                    )
                    for hit in dense_hits:
                        hit["channel"] = "dense"
                    hits.extend(dense_hits)

            # TF-IDF 检索
            vectorizer = book_index.vectorizers.get(target)
            matrix = book_index.matrices.get(target)

            if vectorizer is not None and matrix is not None:
                tfidf_hits = self._tfidf_search(
                    query,
                    docs,
                    vectorizer,
                    matrix,
                    target,
                    top_k,
                    doc_indices=doc_indices,
                )
                for hit in tfidf_hits:
                    hit["channel"] = "sparse"
                hits.extend(tfidf_hits)
            else:
                # 回退到字符级匹配
                fallback_hits = self._sparse_fallback(query, docs, target)
                for hit in fallback_hits:
                    hit["channel"] = "fallback"
                hits.extend(fallback_hits)

        # 使用 RRF 合并多通道结果
        merged = reciprocal_rank_fusion(hits, k=60)

        # 关键词加分（作为后处理，不影响 RRF 主排序）
        key_terms = self._extract_key_terms(query)
        logger.debug(f"Key terms extracted from query: {key_terms}")
        if key_terms:
            char_names = character_names or set()
            term_weights = {}
            for term in key_terms:
                if any(suffix in term for suffix in ["术", "决", "功", "法", "丹", "符", "剑", "阵"]):
                    term_weights[term] = 3.0
                elif term in char_names:
                    term_weights[term] = 0.5
                else:
                    term_weights[term] = 1.0

            for item in merged:
                doc_text = item.get("document", {}).get("text", "")
                total_weight = sum(term_weights.values())
                matched_weight = sum(term_weights.get(term, 1.0) for term in key_terms if term in doc_text)
                coverage = matched_weight / total_weight if total_weight > 0 else 0

                if coverage > 0:
                    original_score = item["score"]
                    item["score"] = item["score"] * (1 + coverage * 0.3)
                    logger.debug(f"RRF + keyword boost: coverage={coverage:.2f}, {original_score:.4f} -> {item['score']:.4f}")

        merged.sort(key=lambda item: item["score"], reverse=True)

        return [
            Hit(target=item["target"], document=item["document"], score=item["score"])
            for item in merged[:top_k]
        ]

    def _extract_key_terms(self, query: str) -> list[str]:
        """从查询中提取关键名词术语。

        使用 jieba 分词提取有意义的名词。
        """
        terms = []

        # 提取引号内的词（精确匹配）
        quoted = re.findall(r'[「」『』"\'"]([^「」『』"\']+)[「」『』"\'"]', query)
        terms.extend(quoted)

        # 使用 jieba 分词提取名词
        words = pseg.cut(query)
        stopwords = {"什么", "时候", "是", "在", "的", "了", "吗", "呢", "啊", "怎么", "如何", "为什么", "谁", "哪", "哪里", "怎样"}

        for word, flag in words:
            # 提取名词、动词（技能相关）、人名
            if len(word) >= 2 and word not in stopwords:
                # n: 名词, nr: 人名, ns: 地名, nt: 机构名, nz: 其他专名
                # v: 动词, vn: 名动词
                # l: 习用语, i: 成语
                if flag.startswith(('n', 'v', 'l', 'i')) or flag == 'nz':
                    terms.append(word)

        # 去重并返回
        return list(dict.fromkeys(terms))

    def _in_scope(self, doc: dict[str, Any], chapter_scope: list[int]) -> bool:
        """Check if document is within chapter scope."""
        chapter = doc.get("chapter")
        if chapter is None:
            # For character cards, check active_range
            active_range = doc.get("active_range") or doc.get("chapter_span")
            if active_range and len(active_range) >= 2:
                return active_range[0] <= max(chapter_scope) and active_range[1] >= min(chapter_scope)
            return True  # No chapter info, include by default
        if len(chapter_scope) == 1:
            return chapter == chapter_scope[0]
        return min(chapter_scope) <= chapter <= max(chapter_scope)

    def _exact_character_hits(
        self, query: str, docs: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Find exact alias matches for character cards."""
        hits = []
        for doc in docs:
            values = [
                doc.get("canonical_name", ""),
                *doc.get("aliases", []),
                *doc.get("titles", []),
            ]
            if any(value and value in query for value in values):
                hits.append({
                    "target": "character_card",
                    "document_id": doc["id"],
                    "document": doc,
                    "score": 1.0,
                })
        return hits

    def _tfidf_search(
        self,
        query: str,
        docs: list[dict[str, Any]],
        vectorizer: Any,
        matrix: Any,
        target: str,
        top_k: int,
        doc_indices: list[int] | None = None,
    ) -> list[dict[str, Any]]:
        """使用 TF-IDF 进行检索。

        Args:
            query: 查询文本
            docs: 文档列表
            vectorizer: TF-IDF vectorizer
            matrix: TF-IDF 矩阵
            target: 检索目标名称
            top_k: 返回数量
            doc_indices: docs 对应的原始 matrix 行号

        Returns:
            命中结果列表
        """
        if not docs or matrix is None:
            return []

        query_vec = vectorizer.transform([query])
        scores = (matrix @ query_vec.T).toarray().ravel()
        candidate_indices = doc_indices or list(range(len(docs)))
        ranked = sorted(
            (
                (doc_pos, matrix_index, float(scores[matrix_index]))
                for doc_pos, matrix_index in enumerate(candidate_indices)
                if matrix_index < len(scores)
            ),
            key=lambda item: item[2],
            reverse=True,
        )[:top_k]

        hits = []
        for doc_pos, _matrix_index, score in ranked:
            if score > 0 and doc_pos < len(docs):
                hits.append({
                    "target": target,
                    "document_id": docs[doc_pos].get("id", f"doc-{doc_pos}"),
                    "document": docs[doc_pos],
                    "score": score,
                })
        return hits

    def _dense_search(
        self,
        query_vector: list[float],
        vector_store: "BaseVectorStore | None",
        target: str,
        top_k: int,
        chapter_scope: list[int] | None = None,
    ) -> list[dict[str, Any]]:
        """使用向量搜索进行检索。

        Args:
            query_vector: 查询向量
            vector_store: 向量存储实例
            target: 检索目标名称
            top_k: 返回数量
            chapter_scope: 章节范围过滤

        Returns:
            命中结果列表
        """
        if vector_store is None:
            return []

        try:
            search_k = top_k * self._overfetch_factor if chapter_scope else top_k
            results = vector_store.search(query_vector, top_k=search_k)
        except Exception as e:
            logger.warning(f"Vector search failed for target={target}: {e}")
            return []

        hits = []
        for result in results:
            if chapter_scope and not self._in_scope(result.document, chapter_scope):
                continue
            hits.append({
                "target": target,
                "document_id": result.id,
                "document": result.document,
                "score": result.score,
            })
            if len(hits) >= top_k:
                break
        return hits

    def _sparse_fallback(
        self, query: str, docs: list[dict[str, Any]], target: str
    ) -> list[dict[str, Any]]:
        """使用 jieba 分词进行词级匹配，并过滤停用词。"""
        text_field = TARGET_PROFILES[target]["text_field"]
        
        # 1. 对查询进行分词并过滤无意义字符/停用词
        query_words = [w.strip() for w in jieba.cut(query) if w.strip()]
        stopwords = {"的", "了", "在", "是", "我", "你", "他", "它", "们", "这", "那", "之", "与", "及", "有", "无", "不", "而", "何", "谁", "吗", "呢", "啊", "吧", "呀", "的", "了", "在"}
        filtered_query_words = [w for w in query_words if w not in stopwords]
        
        # 如果过滤后没有有效词，则退回到使用全部非空分词
        if not filtered_query_words:
            filtered_query_words = query_words
        if not filtered_query_words:
            return []
            
        results = []
        for doc in docs:
            text = str(doc.get(text_field, ""))
            if not text:
                continue
            
            # 计算词重合度
            overlap_count = 0
            for word in filtered_query_words:
                if word in text:
                    overlap_count += 1
            
            if overlap_count > 0:
                score = overlap_count / len(filtered_query_words)
                results.append({
                    "target": target,
                    "document_id": doc.get("id", ""),
                    "document": doc,
                    "score": score,
                })
        return results

    def _dedupe_candidates(
        self, candidates: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Deduplicate candidates by (target, document_id)."""
        bucket: dict[tuple[str, str], dict[str, Any]] = {}
        for item in candidates:
            key = (item["target"], item["document_id"])
            best = bucket.get(key)
            if best is None or item["score"] > best["score"]:
                bucket[key] = item
        return list(bucket.values())
