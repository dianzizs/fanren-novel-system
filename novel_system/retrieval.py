from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from .indexing import LoadedBookIndex, scope_filter


@dataclass(slots=True)
class RetrievalHit:
    target: str
    document: dict[str, Any]
    score: float


class HybridRetriever:
    def __init__(self, book_index: LoadedBookIndex) -> None:
        self.book_index = book_index

    def retrieve(
        self,
        query: str,
        targets: list[str],
        chapter_scope: list[int],
        top_k: int = 6,
        simulate: str | None = None,
    ) -> list[RetrievalHit]:
        hits: list[RetrievalHit] = []
        for target in targets:
            if simulate == "character_card_index_miss" and target == "character_card":
                continue
            target_hits = self._search_target(query, target, chapter_scope, top_k=max(3, top_k))
            hits.extend(target_hits)
        hits.sort(key=lambda item: item.score, reverse=True)
        deduped: list[RetrievalHit] = []
        seen: set[tuple[str, str]] = set()
        for hit in hits:
            key = (hit.target, hit.document["id"])
            if key in seen:
                continue
            seen.add(key)
            deduped.append(hit)
            if len(deduped) >= top_k:
                break
        return deduped

    def _search_target(
        self,
        query: str,
        target: str,
        chapter_scope: list[int],
        top_k: int,
    ) -> list[RetrievalHit]:
        documents = self.book_index.corpora.get(target, [])
        vectorizer = self.book_index.vectorizers.get(target)
        matrix = self.book_index.matrices.get(target)
        if not documents or vectorizer is None or matrix is None:
            return []
        query_vec = vectorizer.transform([query])
        scores = (matrix @ query_vec.T).toarray().ravel()
        if not len(scores):
            return []
        if chapter_scope:
            allowed_indexes = [
                idx
                for idx, document in enumerate(documents)
                if scope_filter(int(document.get("chapter", 0)), chapter_scope)
            ]
        else:
            allowed_indexes = list(range(len(documents)))
        if not allowed_indexes:
            return []
        filtered_scores = np.array([scores[idx] for idx in allowed_indexes])
        ranked = np.argsort(filtered_scores)[::-1][: top_k * 4]
        hits: list[RetrievalHit] = []
        for filtered_index in ranked:
            index = allowed_indexes[int(filtered_index)]
            score = float(scores[index])
            if score <= 0:
                continue
            document = documents[int(index)]
            hits.append(RetrievalHit(target=target, document=document, score=score))
            if len(hits) >= top_k:
                break
        return hits
