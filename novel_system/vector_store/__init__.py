"""Vector Store module for semantic search."""

from .base import BaseVectorStore, VectorSearchResult
from .faiss_store import FAISSVectorStore

__all__ = [
    "BaseVectorStore",
    "VectorSearchResult",
    "FAISSVectorStore",
]
