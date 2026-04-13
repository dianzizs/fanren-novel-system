"""Base types and protocols for search."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class RetrievalCandidate:
    """A retrieval candidate with score and metadata."""

    target: str
    document_id: str
    document: dict[str, Any]
    score: float
    backend_scores: dict[str, float] = field(default_factory=dict)
    explanations: list[str] = field(default_factory=list)


class SparseBackend(Protocol):
    """Protocol for sparse (TF-IDF) search backend."""

    def search(self, query: str, top_k: int) -> list[RetrievalCandidate]:
        """Search for candidates using sparse matching."""
        ...


class DenseBackend(Protocol):
    """Protocol for dense (embedding) search backend."""

    def search(self, query: str, top_k: int) -> list[RetrievalCandidate]:
        """Search for candidates using dense similarity."""
        ...
