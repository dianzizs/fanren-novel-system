"""Artifact builders for novel system indexing.

This package provides stable intermediate artifacts:
- scene_segments: Scene-level text segments with metadata
- character_registry: Canonical character entries with alias resolution
- targets: Retrieval targets (chapter_chunks, event_timeline, character_card)
"""

__all__ = [
    "scene_segments",
    "character_registry",
    "targets",
]
