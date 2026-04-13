"""Search orchestrator for multi-target retrieval."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .profiles import TARGET_PROFILES


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

    def retrieve(
        self,
        *,
        book_index: Any,
        query: str,
        targets: list[str],
        chapter_scope: list[int],
        top_k: int,
    ) -> list[Hit]:
        """Retrieve candidates from multiple targets.

        Args:
            book_index: Book index with corpora dict.
            query: User query string.
            targets: List of target names to search.
            chapter_scope: Chapter range for filtering.
            top_k: Maximum results to return.

        Returns:
            List of Hit objects sorted by score.
        """
        hits: list[dict[str, Any]] = []
        for target in targets:
            docs = list(book_index.corpora.get(target, []))
            # Filter by chapter scope
            if chapter_scope:
                docs = [doc for doc in docs if self._in_scope(doc, chapter_scope)]

            # 特殊处理：character_card 精确别名匹配
            if target == "character_card":
                alias_hits = self._exact_character_hits(query, docs)
                hits.extend(alias_hits)

            # TF-IDF 检索
            vectorizer = book_index.vectorizers.get(target)
            matrix = book_index.matrices.get(target)

            if vectorizer is not None and matrix is not None:
                tfidf_hits = self._tfidf_search(query, docs, vectorizer, matrix, target, top_k)
                hits.extend(tfidf_hits)
            else:
                # 回退到字符级匹配
                hits.extend(self._sparse_fallback(query, docs, target))

        deduped = self._dedupe_candidates(hits)
        deduped.sort(key=lambda item: item["score"], reverse=True)
        return [
            Hit(target=item["target"], document=item["document"], score=item["score"])
            for item in deduped[:top_k]
        ]

    def _in_scope(self, doc: dict[str, Any], chapter_scope: list[int]) -> bool:
        """Check if document is within chapter scope."""
        chapter = doc.get("chapter")
        if chapter is None:
            # For character cards, check active_range
            active_range = doc.get("active_range") or doc.get("chapter_span")
            if active_range and len(active_range) >= 2:
                return active_range[0] <= max(chapter_scope) and active_range[1] >= min(chapter_scope)
            return True  # No chapter info, include by default
        return chapter in chapter_scope

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
    ) -> list[dict[str, Any]]:
        """使用 TF-IDF 进行检索。

        Args:
            query: 查询文本
            docs: 文档列表
            vectorizer: TF-IDF vectorizer
            matrix: TF-IDF 矩阵
            target: 检索目标名称
            top_k: 返回数量

        Returns:
            命中结果列表
        """
        if not docs or matrix is None:
            return []

        query_vec = vectorizer.transform([query])
        scores = (matrix @ query_vec.T).toarray().ravel()
        top_indices = scores.argsort()[-top_k:][::-1]

        hits = []
        for idx in top_indices:
            if scores[idx] > 0 and idx < len(docs):
                hits.append({
                    "target": target,
                    "document_id": docs[idx].get("id", f"doc-{idx}"),
                    "document": docs[idx],
                    "score": float(scores[idx]),
                })
        return hits

    def _sparse_fallback(
        self, query: str, docs: list[dict[str, Any]], target: str
    ) -> list[dict[str, Any]]:
        """Simple character-level overlap scoring."""
        text_field = TARGET_PROFILES[target]["text_field"]
        results = []
        for doc in docs:
            text = str(doc.get(text_field, ""))
            # Simple character overlap scoring
            overlap = sum(1 for char in query if char and char in text)
            if overlap > 0:
                score = overlap / max(1, len(query))
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
