"""Public indexing pipeline for building book artifacts.

This module provides the main entry point for building all artifacts
from parsed chapter data.
"""
from __future__ import annotations

from typing import Any

from .artifacts.character_registry import CharacterRegistryBuilder
from .artifacts.scene_segments import SceneSegmentBuilder
from .artifacts.targets import build_chapter_chunks, build_character_cards, build_event_timeline
from .indexing import ALIAS_MAP


def build_book_artifacts(chapters: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Build all artifacts from parsed chapters.

    This is the main entry point for indexing. It orchestrates:
    1. Scene segmentation
    2. Character registry building
    3. Target artifact building (chunks, events, cards)

    Args:
        chapters: List of chapter dicts with 'chapter', 'title', 'text', 'paragraphs' keys.

    Returns:
        Dict mapping artifact names to lists of artifact dicts.
    """
    # Step 1: Build scene segments
    scenes = SceneSegmentBuilder().build(chapters)

    # Step 2: Build character registry
    registry = CharacterRegistryBuilder(seed_aliases=ALIAS_MAP).build(scenes)

    # Step 3: Build target artifacts
    events = build_event_timeline(scenes)
    cards = build_character_cards(registry, scenes, events)

    return {
        "scene_segments": scenes,
        "character_registry": registry,
        "chapter_chunks": build_chapter_chunks(scenes),
        "chapter_summaries": [],
        "event_timeline": events,
        "character_card": cards,
        "relationship_graph": [],
        "world_rule": [],
        "canon_memory": [],
        "recent_plot": [],
        "style_samples": [],
        "vision_parse": [],
    }
