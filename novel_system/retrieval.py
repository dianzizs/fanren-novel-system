"""Retrieval compatibility layer.

This module provides backward-compatible retrieval by delegating to
the new SearchOrchestrator while preserving the original HybridRetriever
interface for legacy code.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .reranker.base import BaseReranker
from .search.orchestrator import SearchOrchestrator


@dataclass
class RetrievalHit:
    """A retrieval hit with target, document, and score."""
    target: str
    document: dict[str, Any]
    score: float


class HybridRetriever:
    """Hybrid retriever that delegates to SearchOrchestrator.

    This class maintains backward compatibility with the existing API
    while using the new search orchestration internally.
    """

    def __init__(
        self,
        book_index: Any,
        overfetch_factor: int = 10,
        reranker: BaseReranker | None = None,
    ) -> None:
        self.book_index = book_index
        self.orchestrator = SearchOrchestrator(overfetch_factor=overfetch_factor)
        self.reranker = reranker

    def retrieve(
        self,
        query: str,
        targets: list[str],
        chapter_scope: list[int],
        top_k: int = 6,
        simulate: str | None = None,
        query_embedding: list[float] | None = None,
    ) -> list[RetrievalHit]:
        """Retrieve documents using the search orchestrator.

        Args:
            query: User query string.
            targets: List of target names to search.
            chapter_scope: Chapter range for filtering.
            top_k: Maximum results to return.
            simulate: Simulation mode for testing (deprecated).
            query_embedding: Optional query vector for dense search.

        Returns:
            List of RetrievalHit objects.
        """
        raw_hits = self.orchestrator.retrieve(
            book_index=self.book_index,
            query=query,
            targets=targets,
            chapter_scope=chapter_scope,
            top_k=top_k,
            query_embedding=query_embedding,
        )
        hits = [
            RetrievalHit(target=hit.target, document=hit.document, score=hit.score)
            for hit in raw_hits
        ]
        if self.reranker is not None and hits:
            reranked = self.reranker.rerank(
                query=query,
                candidates=hits,
                top_k=top_k,
                scope=chapter_scope,
            )
            hits = [
                RetrievalHit(
                    target=r.target,
                    document=r.document,
                    score=r.final_score,
                )
                for r in reranked
            ]
        return hits

