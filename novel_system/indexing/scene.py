from __future__ import annotations
from dataclasses import dataclass
from typing import Any
from collections import Counter
import jieba.posseg as pseg
from .constants import (
    PERSON_RE,
    TITLE_PERSON_RE,
    STOP_NAMES,
    BAD_NAME_ENDINGS,
    LOCATION_SHIFT_RE,
)

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


class SceneSegmentBuilder:
    """Builds scene segments from parsed chapters.

    Scenes are split on location shifts and carry character mentions.
    Each scene gets a stable ID for cross-referencing.
    """

    def build(self, chapters: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Build scene segments from chapters.

        Args:
            chapters: List of chapter dicts with 'chapter', 'title', 'paragraphs' keys.

        Returns:
            List of scene segment dicts with metadata.
        """
        scenes: list[dict[str, Any]] = []
        for chapter in chapters:
            current: list[str] = []
            start_index = 0
            scene_index = 0
            for paragraph_index, paragraph in enumerate(chapter.get("paragraphs", [])):
                if current and self._is_boundary(current[-1], paragraph):
                    scenes.append(
                        self._make_scene(chapter, scene_index, start_index, paragraph_index - 1, current)
                    )
                    scene_index += 1
                    current = []
                    start_index = paragraph_index
                current.append(paragraph)
            if current:
                scenes.append(
                    self._make_scene(chapter, scene_index, start_index, start_index + len(current) - 1, current)
                )
        return scenes

    def _is_boundary(self, previous: str, current: str) -> bool:
        """Detect if there's a scene boundary between paragraphs."""
        return bool(LOCATION_SHIFT_RE.search(current) and previous != current)

    def _make_scene(
        self,
        chapter: dict[str, Any],
        scene_index: int,
        start_index: int,
        end_index: int,
        paragraphs: list[str],
    ) -> dict[str, Any]:
        """Create a scene segment dict."""
        text = "\n".join(paragraphs)
        mentions = self._extract_person_names(text)
        ranked_mentions = [name for name, _ in Counter(mentions).most_common(6)]
        return {
            "id": f"ch{chapter['chapter']}-scene{scene_index}",
            "chapter": chapter["chapter"],
            "scene_index": scene_index,
            "title": chapter["title"],
            "text": text,
            "paragraph_start": start_index,
            "paragraph_end": end_index,
            "char_start": 0,
            "char_end": len(text),
            "scene_summary": text[:120],
            "major_characters": ranked_mentions[:3],
            "raw_character_mentions": ranked_mentions,
            "event_ids": [],
            "spoiler_level": "current",
            "prev_scene_id": None if scene_index == 0 else f"ch{chapter['chapter']}-scene{scene_index - 1}",
            "next_scene_id": None,
        }

    def _extract_person_names(self, text: str) -> list[str]:
        """Extract person names using POS tagging and surname patterns.

        Combines two strategies:
        1. jieba POS tagging (nr = person name) for segmentation-based detection
        2. Regex patterns (PERSON_RE, TITLE_PERSON_RE) for surname-based fallback

        Results are merged, deduplicated, and filtered.
        """
        names: list[str] = []

        # Strategy 1: jieba POS tagging — identify words tagged as person names (nr)
        for word in pseg.cut(text):
            if word.flag == "nr" and len(word.word) >= 2:
                candidate = word.word.strip()
                if (
                    candidate not in STOP_NAMES
                    and candidate[-1] not in BAD_NAME_ENDINGS
                    and not candidate.endswith(("门", "帮", "山", "谷", "功", "法"))
                ):
                    names.append(candidate)

        # Strategy 2: regex patterns (surname + title based)
        for regex in (PERSON_RE, TITLE_PERSON_RE):
            for item in regex.findall(text):
                candidate = item.strip()
                if (
                    len(candidate) < 2
                    or candidate in STOP_NAMES
                    or candidate[-1] in BAD_NAME_ENDINGS
                ):
                    continue
                if candidate.endswith("门") or candidate.endswith("帮") or candidate.endswith("山") or candidate.endswith("谷"):
                    continue
                names.append(candidate)

        frequency = Counter(names)
        return [name for name, _ in frequency.most_common() if name not in STOP_NAMES]


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
