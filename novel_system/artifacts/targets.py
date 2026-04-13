"""Target artifact builders.

This module provides builders for the three primary retrieval targets:
- chapter_chunks: Text chunks with scene metadata
- event_timeline: Event entries derived from scenes
- character_card: Character cards backed by the registry
"""
from __future__ import annotations

from typing import Any


def build_chapter_chunks(
    scenes: list[dict[str, Any]],
    *,
    chunk_size: int = 420,
    overlap: int = 80,
) -> list[dict[str, Any]]:
    """Build chapter chunks from scene segments.

    Each chunk inherits scene metadata (major_characters, event_ids, spoiler_level).

    Args:
        scenes: List of scene segment dicts.
        chunk_size: Maximum characters per chunk.
        overlap: Character overlap between consecutive chunks.

    Returns:
        List of chunk dicts with scene metadata.
    """
    chunks: list[dict[str, Any]] = []
    for scene in scenes:
        text = scene["text"]
        start = 0
        chunk_index = 0
        while start < len(text):
            end = min(len(text), start + chunk_size)
            snippet = text[start:end].strip()
            if snippet:
                chunks.append(
                    {
                        "id": f"{scene['id']}-chunk{chunk_index}",
                        "chapter": scene["chapter"],
                        "title": scene["title"],
                        "target": "chapter_chunks",
                        "text": snippet,
                        "source": f"第{scene['chapter']}章 {scene['title']}",
                        "scene_id": scene["id"],
                        "scene_index": scene["scene_index"],
                        "chunk_index_in_scene": chunk_index,
                        "chunk_count_in_scene": None,
                        "major_characters": list(scene.get("major_characters", [])),
                        "event_ids": list(scene.get("event_ids", [])),
                        "spoiler_level": scene.get("spoiler_level", "current"),
                        "paragraph_start": scene["paragraph_start"],
                        "paragraph_end": scene["paragraph_end"],
                        "char_start": scene["char_start"] + start,
                        "char_end": scene["char_start"] + end,
                    }
                )
                chunk_index += 1
            if end >= len(text):
                break
            start = max(0, end - overlap)
        # Update chunk_count_in_scene for all chunks of this scene
        total = chunk_index
        for item in chunks[-total:]:
            item["chunk_count_in_scene"] = total
    return chunks


def build_event_timeline(
    scenes: list[dict[str, Any]],
    *,
    max_events_per_scene: int = 1,
) -> list[dict[str, Any]]:
    """Build event timeline from scene segments.

    Each scene generates one event entry with participants from major_characters.

    Args:
        scenes: List of scene segment dicts.
        max_events_per_scene: Maximum events per scene (currently 1).

    Returns:
        List of event dicts linked to scenes.
    """
    events: list[dict[str, Any]] = []
    for scene in scenes:
        event_id = f"event-{scene['id']}-0"
        event = {
            "event_id": event_id,
            "id": event_id,
            "chapter": scene["chapter"],
            "scene_id": scene["id"],
            "title": f"第{scene['chapter']}章事件",
            "target": "event_timeline",
            "summary": scene.get("scene_summary", scene["text"][:120]),
            "text": scene.get("scene_summary", scene["text"][:120]),
            "participants": list(scene.get("major_characters", [])),
            "location": scene["title"],
            "event_type": "scene_summary",
            "preceding_event_ids": [events[-1]["event_id"]] if events else [],
            "following_event_ids": [],
            "spoiler_level": scene.get("spoiler_level", "current"),
            "source": f"第{scene['chapter']}章 {scene['title']}",
        }
        if events:
            events[-1]["following_event_ids"] = [event_id]
        events.append(event)
    return events


def build_character_cards(
    registry: list[dict[str, Any]],
    scenes: list[dict[str, Any]],
    events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build character cards from registry, scenes, and events.

    Cards combine registry metadata with scene evidence and event participation.

    Args:
        registry: List of character registry entries.
        scenes: List of scene segment dicts.
        events: List of event dicts.

    Returns:
        List of character card dicts.
    """
    scene_map = {scene["id"]: scene for scene in scenes}
    cards: list[dict[str, Any]] = []
    for entry in registry:
        # Find events where this character participates
        related_events = [
            event["event_id"]
            for event in events
            if entry["canonical_name"] in event.get("participants", [])
        ]
        # Get evidence snippets from scenes
        snippets = [
            scene_map[scene_id]["text"][:120]
            for scene_id in entry.get("evidence_scene_ids", [])
            if scene_id in scene_map
        ]
        cards.append(
            {
                "id": f"character-{entry['canonical_name']}",
                "character_id": entry["character_id"],
                "canonical_name": entry["canonical_name"],
                "aliases": list(entry.get("aliases", [])),
                "titles": list(entry.get("titles", [])),
                "chapter": entry["active_range"][0],
                "chapter_span": list(entry["active_range"]),
                "active_range": list(entry["active_range"]),
                "target": "character_card",
                "summary": snippets[0] if snippets else entry["canonical_name"],
                "retrieval_text": " ".join([entry["canonical_name"], *entry.get("aliases", []), *snippets[:2]]).strip(),
                "key_scene_ids": list(entry.get("evidence_scene_ids", [])),
                "related_event_ids": related_events,
                "source": f"{entry['canonical_name']}人物卡",
            }
        )
    return cards
