"""Character registry for alias resolution and identity tracking.

The character registry provides:
- Canonical name to alias mapping
- Active chapter range tracking
- Co-occurring character tracking
- Evidence scene ID tracking
"""
from __future__ import annotations

from typing import Any


class CharacterRegistryBuilder:
    """Builds character registry from scene segments.

    The registry resolves aliases to canonical names and tracks
    character appearances across chapters.
    """

    def __init__(self, seed_aliases: dict[str, list[str]] | None = None) -> None:
        """Initialize with optional seed alias map.

        Args:
            seed_aliases: Map of canonical names to their known aliases.
                         e.g., {"韩立": ["二愣子"], "墨大夫": ["墨老"]}
        """
        self.seed_aliases = seed_aliases or {}
        self.alias_to_canonical = {
            alias: canonical
            for canonical, aliases in self.seed_aliases.items()
            for alias in aliases
        }

    def build(self, scenes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Build character registry from scene segments.

        Args:
            scenes: List of scene segment dicts with character mentions.

        Returns:
            List of character registry entries sorted by first appearance.
        """
        buckets: dict[str, dict[str, Any]] = {}
        for scene in scenes:
            seen_in_scene: set[str] = set()
            for mention in scene.get("raw_character_mentions", []):
                canonical = self.alias_to_canonical.get(mention, mention)
                entry = buckets.setdefault(
                    canonical,
                    {
                        "character_id": f"char-{canonical}",
                        "canonical_name": canonical,
                        "aliases": [],
                        "titles": [],
                        "name_variants": [canonical],
                        "first_seen_chapter": scene["chapter"],
                        "last_seen_chapter": scene["chapter"],
                        "active_range": [scene["chapter"], scene["chapter"]],
                        "evidence_scene_ids": [],
                        "co_occurring_characters": [],
                        "confidence": 1.0 if mention == canonical else 0.9,
                    },
                )
                if mention != canonical and mention not in entry["aliases"]:
                    entry["aliases"].append(mention)
                    entry["name_variants"].append(mention)
                entry["first_seen_chapter"] = min(entry["first_seen_chapter"], scene["chapter"])
                entry["last_seen_chapter"] = max(entry["last_seen_chapter"], scene["chapter"])
                entry["active_range"] = [entry["first_seen_chapter"], entry["last_seen_chapter"]]
                if scene["id"] not in entry["evidence_scene_ids"]:
                    entry["evidence_scene_ids"].append(scene["id"])
                seen_in_scene.add(canonical)
            # Track co-occurring characters
            for canonical in seen_in_scene:
                others = sorted(name for name in seen_in_scene if name != canonical)
                for other in others:
                    if other not in buckets[canonical]["co_occurring_characters"]:
                        buckets[canonical]["co_occurring_characters"].append(other)
        return sorted(buckets.values(), key=lambda item: (item["first_seen_chapter"], item["canonical_name"]))
