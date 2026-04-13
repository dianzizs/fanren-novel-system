"""Search package for retrieval orchestration.

This package provides:
- base: Core types and protocols
- profiles: Target profile definitions
- sparse: TF-IDF sparse backend
- dense: Dense embedding backend
- hybrid: Hybrid score fusion
- rerank: Re-ranking logic
- orchestrator: Multi-target retrieval orchestration
"""

from .orchestrator import SearchOrchestrator
from .base import RetrievalCandidate

__all__ = [
    "SearchOrchestrator",
    "RetrievalCandidate",
]
