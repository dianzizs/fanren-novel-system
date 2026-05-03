"""Character registry for alias resolution and identity tracking.

The character registry provides:
- Canonical name to alias mapping
- Active chapter range tracking
- Co-occurring character tracking
- Evidence scene ID tracking
- Evidence-based candidate filtering (frequency, chapter span, scene evidence)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class FilterThresholds:
    """Thresholds for evidence-based candidate filtering.

    Characters below these thresholds are filtered out, unless they are
    seed characters (known canonical names from seed_aliases).
    """
    min_frequency: int = 2
    min_chapter_span: int = 1
    min_scene_count: int = 1


class CharacterRegistryBuilder:
    """Builds character registry from scene segments.

    The registry resolves aliases to canonical names, tracks
    character appearances across chapters, and filters candidates
    based on evidence (frequency, chapter span, scene count).
    """

    def __init__(
        self,
        seed_aliases: dict[str, list[str]] | None = None,
        thresholds: FilterThresholds | None = None,
    ) -> None:
        """Initialize with optional seed alias map and filter thresholds.

        Args:
            seed_aliases: Map of canonical names to their known aliases.
                         e.g., {"韩立": ["二愣子"], "墨大夫": ["墨老"]}
            thresholds: Evidence thresholds for filtering candidates.
        """
        self.seed_aliases = seed_aliases or {}
        self.thresholds = thresholds or FilterThresholds()
        self.alias_to_canonical = {
            alias: canonical
            for canonical, aliases in self.seed_aliases.items()
            for alias in aliases
        }
        # Seed characters are always kept regardless of evidence
        self.seed_canonical_names = set(self.seed_aliases.keys())

    def build(self, scenes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Build character registry from scene segments.

        Applies evidence-based filtering:
        - Frequency evidence: minimum number of mentions
        - Chapter span evidence: minimum number of unique chapters
        - Scene evidence: minimum number of unique scenes

        Seed characters (from seed_aliases keys) are always kept.

        Args:
            scenes: List of scene segment dicts with character mentions.

        Returns:
            List of character registry entries sorted by first appearance.
        """
        # Track raw evidence for each candidate
        raw_buckets: dict[str, dict[str, Any]] = {}
        mention_counts: dict[str, int] = {}

        for scene in scenes:
            seen_in_scene: set[str] = set()
            mentions_in_scene = scene.get("raw_character_mentions", [])
            for mention in mentions_in_scene:
                canonical = self.alias_to_canonical.get(mention, mention)
                mention_counts[canonical] = mention_counts.get(canonical, 0) + 1
                entry = raw_buckets.setdefault(
                    canonical,
                    {
                        "character_id": f"char-{canonical}",
                        "canonical_name": canonical,
                        "aliases": [],
                        "titles": [],
                        "name_variants": [canonical],
                        "first_seen_chapter": scene["chapter"],
                        "last_seen_chapter": scene["chapter"],
                        "chapters": {scene["chapter"]},
                        "evidence_scene_ids": [],
                        "co_occurring_characters": [],
                    },
                )
                if mention != canonical and mention not in entry["aliases"]:
                    entry["aliases"].append(mention)
                    entry["name_variants"].append(mention)
                entry["first_seen_chapter"] = min(entry["first_seen_chapter"], scene["chapter"])
                entry["last_seen_chapter"] = max(entry["last_seen_chapter"], scene["chapter"])
                entry["chapters"].add(scene["chapter"])
                if scene["id"] not in entry["evidence_scene_ids"]:
                    entry["evidence_scene_ids"].append(scene["id"])
                seen_in_scene.add(canonical)
            # Track co-occurring characters
            for canonical in seen_in_scene:
                others = sorted(name for name in seen_in_scene if name != canonical)
                for other in others:
                    if other not in raw_buckets[canonical]["co_occurring_characters"]:
                        raw_buckets[canonical]["co_occurring_characters"].append(other)

        # Filter candidates based on evidence thresholds
        filtered_entries: list[dict[str, Any]] = []
        for canonical, entry in raw_buckets.items():
            frequency = mention_counts.get(canonical, 0)
            chapter_span = len(entry["chapters"])
            scene_count = len(entry["evidence_scene_ids"])

            # Compute confidence based on evidence
            confidence = self._compute_confidence(frequency, chapter_span, scene_count)

            # Check if character passes evidence thresholds
            is_seed = canonical in self.seed_canonical_names
            passes_filter = (
                is_seed
                or (
                    frequency >= self.thresholds.min_frequency
                    and chapter_span >= self.thresholds.min_chapter_span
                    and scene_count >= self.thresholds.min_scene_count
                )
            )

            if passes_filter:
                filtered_entries.append({
                    "character_id": entry["character_id"],
                    "canonical_name": entry["canonical_name"],
                    "aliases": list(entry["aliases"]),
                    "titles": list(entry["titles"]),
                    "name_variants": list(entry["name_variants"]),
                    "first_seen_chapter": entry["first_seen_chapter"],
                    "last_seen_chapter": entry["last_seen_chapter"],
                    "active_range": [entry["first_seen_chapter"], entry["last_seen_chapter"]],
                    "evidence_scene_ids": list(entry["evidence_scene_ids"]),
                    "co_occurring_characters": list(entry["co_occurring_characters"]),
                    # Primary evidence fields (for backward compatibility)
                    "frequency": frequency,
                    "chapter_span": chapter_span,
                    "scene_count": scene_count,
                    # Additional detail fields
                    "frequency_evidence": frequency,
                    "chapter_span_evidence": chapter_span,
                    "scene_evidence": scene_count,
                    "confidence": round(confidence, 3),
                })

        # Sort deterministically: by first appearance, then by name for stability
        return sorted(filtered_entries, key=lambda item: (item["first_seen_chapter"], item["canonical_name"]))

    def _compute_confidence(self, frequency: int, chapter_span: int, scene_count: int) -> float:
        """Compute confidence score based on evidence.

        Higher evidence → higher confidence.
        Base confidence is 0.5, boosted by evidence.
        """
        base = 0.5
        frequency_boost = min(frequency * 0.05, 0.2)
        chapter_boost = min(chapter_span * 0.1, 0.15)
        scene_boost = min(scene_count * 0.05, 0.15)
        return min(base + frequency_boost + chapter_boost + scene_boost, 1.0)
