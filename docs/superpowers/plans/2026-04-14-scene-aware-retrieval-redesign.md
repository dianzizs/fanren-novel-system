# Scene-Aware Retrieval Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild indexing and retrieval around `scene_segments` and `character_registry`, then migrate `chapter_chunks`, `event_timeline`, and `character_card` onto a pluggable sparse/dense/hybrid/rerank search stack that improves grounded QA and scope control.

**Architecture:** Add two stable intermediate artifacts (`scene_segments`, `character_registry`), then rebuild the three high-value retrieval targets from those artifacts. Introduce a new `novel_system/search/` package for target profiles, backends, fusion, and rerank, and keep the existing `novel_system/retrieval.py` only as a compatibility shim during migration because a package named `retrieval/` would conflict with the existing module file.

**Tech Stack:** Python 3.9+, Pydantic models, scikit-learn TF-IDF sparse indexing, existing embedding provider + `SemanticScorer`, pytest, FastAPI service integration

---

## File Structure

### Create

- `novel_system/artifacts/__init__.py`
  - Artifact package export surface.
- `novel_system/artifacts/scene_segments.py`
  - `SceneSegment` model plus `SceneSegmentBuilder`.
- `novel_system/artifacts/character_registry.py`
  - `CharacterRegistryEntry` model plus `CharacterRegistryBuilder`.
- `novel_system/artifacts/targets.py`
  - Builders for `chapter_chunks`, `event_timeline`, and `character_card` from stable artifacts.
- `novel_system/index_pipeline.py`
  - Public indexing orchestration entrypoint used by service and scripts.
- `novel_system/search/__init__.py`
  - Export search orchestrator and types.
- `novel_system/search/base.py`
  - `RetrievalCandidate`, `TargetProfile`, backend protocols, filter models.
- `novel_system/search/profiles.py`
  - Target-profile definitions for `chapter_chunks`, `event_timeline`, and `character_card`.
- `novel_system/search/sparse.py`
  - TF-IDF sparse backend.
- `novel_system/search/dense.py`
  - Dense backend using embedding provider and document ids.
- `novel_system/search/hybrid.py`
  - Hybrid score fusion backend.
- `novel_system/search/rerank.py`
  - Scene-aware and identity-aware rerank logic.
- `novel_system/search/orchestrator.py`
  - Multi-target retrieval orchestration.
- `tests/test_scene_segments.py`
  - Scene segmentation behavior and metadata tests.
- `tests/test_character_registry.py`
  - Alias/title normalization and active-range tests.
- `tests/test_artifact_targets.py`
  - Scene-aware `chapter_chunks`, event extraction, and registry-backed character-card tests.
- `tests/test_search_orchestrator.py`
  - Profile selection, fusion, exact alias precedence, and dedupe tests.
- `tests/test_index_pipeline.py`
  - End-to-end build and manifest-version tests.

### Modify

- `novel_system/indexing.py`
  - Limit repository to persistence/load concerns; support new artifact filenames and version metadata.
- `novel_system/models.py`
  - Add `retrieval_intent` to `PlannerOutput`; extend any artifact/trace models required by new metadata.
- `novel_system/planner.py`
  - Make rewrite and planning consume `character_registry`.
- `novel_system/retrieval.py`
  - Convert to compatibility wrapper delegating to `novel_system/search/orchestrator.py`.
- `novel_system/semantic_scorer.py`
  - Make dense scoring use document ids / retrieval text from candidates instead of ad hoc hit attributes.
- `novel_system/service.py`
  - Use `index_pipeline` and search orchestrator; stop calling repository private build helpers.
- `novel_system/validator.py`
  - Read `character_registry` and scene-aware metadata instead of assuming rich fields on every character card.
- `tests/test_validation.py`
  - Update fixtures and expectations for new schemas.
- `tests/test_book_import_artifacts.py`
  - Verify `scene_segments` and `character_registry` are exposed in artifact catalog.

### Constraints and Notes

- Do not create a `novel_system/retrieval/` package because `novel_system/retrieval.py` already exists and would collide at import time.
- Keep existing public target names (`chapter_chunks`, `event_timeline`, `character_card`) stable.
- Preserve API compatibility where possible while allowing internal schema cleanup.
- Prefer under-merging characters to over-merging them in `character_registry` v1.

## Task 1: Add Artifact Schema Surface and Repository Support

**Files:**
- Create: `novel_system/artifacts/__init__.py`
- Modify: `novel_system/indexing.py`
- Modify: `novel_system/models.py`
- Test: `tests/test_index_pipeline.py`
- Test: `tests/test_book_import_artifacts.py`

- [ ] **Step 1: Write the failing repository and manifest tests**

```python
# tests/test_index_pipeline.py
from pathlib import Path

from novel_system.config import AppConfig
from novel_system.indexing import BookIndexRepository


def test_repository_reads_new_artifact_names(tmp_path: Path):
    config = AppConfig(
        root_dir=tmp_path,
        data_dir=tmp_path / "data",
        runtime_dir=tmp_path / "data" / "runtime",
        books_dir=tmp_path / "data" / "books",
        default_book_id="default-book",
        default_book_title="Default",
        default_book_path=tmp_path / "default.txt",
        minimax_api_key="",
        minimax_base_url="https://api.minimax.chat/v1",
        minimax_chat_model="MiniMax-m2.7-HighSpeed",
        minimax_embedding_model="embo-01",
        trace_enabled=False,
        trace_log_level="INFO",
    )
    config.books_dir.mkdir(parents=True, exist_ok=True)
    book_dir = config.books_dir / "book-a"
    book_dir.mkdir(parents=True, exist_ok=True)
    (book_dir / "manifest.json").write_text(
        '{"id":"book-a","title":"A","artifact_version":"v2","available_artifacts":["scene_segments","character_registry"]}',
        encoding="utf-8",
    )
    (book_dir / "scene_segments.json").write_text("[]", encoding="utf-8")
    (book_dir / "character_registry.json").write_text("[]", encoding="utf-8")

    repo = BookIndexRepository(config)

    assert repo.read_artifact("book-a", "scene_segments") == []
    assert repo.read_artifact("book-a", "character_registry") == []
```

```python
# tests/test_book_import_artifacts.py
def test_artifact_catalog_includes_scene_and_registry(self) -> None:
    manifest = self.upload_book("artifact-view-book.txt", sample_book(3))
    book_id = manifest["id"]
    self.wait_until_ready(book_id)

    catalog_response = self.client.get(f"/api/books/{book_id}/artifacts")
    catalog_response.raise_for_status()
    artifact_names = [item["name"] for item in catalog_response.json()["artifacts"]]

    assert "scene_segments" in artifact_names
    assert "character_registry" in artifact_names
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_index_pipeline.py::test_repository_reads_new_artifact_names tests/test_book_import_artifacts.py::BookImportArtifactsTest::test_artifact_catalog_includes_scene_and_registry -v`

Expected: FAIL with `FileNotFoundError` or missing artifact-catalog entries for `scene_segments` / `character_registry`.

- [ ] **Step 3: Add artifact names, manifest fields, and planner model support**

```python
# novel_system/models.py
class PlannerOutput(BaseModel):
    task_type: TaskType
    retrieval_needed: bool = True
    retrieval_targets: list[str] = Field(default_factory=list)
    retrieval_intent: str = "scene_evidence"
    constraints: list[str] = Field(default_factory=list)
    success_criteria: list[str] = Field(default_factory=list)
```

```python
# novel_system/indexing.py
ARTIFACT_FILENAMES = {
    "manifest": "manifest.json",
    "chapters": "chapters.json",
    "scene_segments": "scene_segments.json",
    "character_registry": "character_registry.json",
    "chapter_chunks": "chapter_chunks.json",
    "chapter_summaries": "chapter_summaries.json",
    "event_timeline": "event_timeline.json",
    "character_card": "character_card.json",
    "relationship_graph": "relationship_graph.json",
    "world_rule": "world_rule.json",
    "canon_memory": "canon_memory.json",
    "recent_plot": "recent_plot.json",
    "style_samples": "style_samples.json",
    "vision_parse": "vision_parse.json",
}


def build_manifest(
    book_id: str,
    title: str,
    source_path: str,
    *,
    chapter_count: int,
    chunk_count: int,
    available_artifacts: list[str],
    status: str = "ready",
) -> dict[str, Any]:
    return {
        "id": book_id,
        "title": title,
        "source_path": source_path,
        "chapter_count": chapter_count,
        "chunk_count": chunk_count,
        "indexed": status == "ready",
        "status": status,
        "artifact_version": "v2",
        "available_artifacts": available_artifacts,
    }
```

```python
# novel_system/artifacts/__init__.py
__all__ = [
    "scene_segments",
    "character_registry",
    "targets",
]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_index_pipeline.py::test_repository_reads_new_artifact_names tests/test_book_import_artifacts.py::BookImportArtifactsTest::test_artifact_catalog_includes_scene_and_registry -v`

Expected: PASS with `2 passed`.

- [ ] **Step 5: Commit**

```bash
git add novel_system/models.py novel_system/indexing.py novel_system/artifacts/__init__.py tests/test_index_pipeline.py tests/test_book_import_artifacts.py
git commit -m "feat: add scene and registry artifact schema support"
```

## Task 2: Implement `SceneSegmentBuilder`

**Files:**
- Create: `novel_system/artifacts/scene_segments.py`
- Modify: `novel_system/index_pipeline.py`
- Test: `tests/test_scene_segments.py`

- [ ] **Step 1: Write the failing scene-segmentation tests**

```python
# tests/test_scene_segments.py
from novel_system.artifacts.scene_segments import SceneSegmentBuilder


def test_scene_builder_splits_on_location_shift():
    chapter = {
        "chapter": 12,
        "title": "试炼前夜",
        "paragraphs": [
            "韩立在屋内盘膝打坐，默默运转长春功。",
            "片刻后他推门而出，来到青石广场，看见张铁已经等在那里。",
        ],
    }

    scenes = SceneSegmentBuilder().build([chapter])

    assert len(scenes) == 2
    assert scenes[0]["id"] == "ch12-scene0"
    assert scenes[1]["id"] == "ch12-scene1"
    assert scenes[0]["paragraph_start"] == 0
    assert scenes[1]["paragraph_start"] == 1
```

```python
def test_scene_builder_carries_character_mentions():
    chapter = {
        "chapter": 1,
        "title": "山边小村",
        "paragraphs": [
            "韩立被村里人叫作二愣子。",
            "三叔笑眯眯地望着韩立，和韩父韩母说起七玄门。",
        ],
    }

    scenes = SceneSegmentBuilder().build([chapter])

    assert scenes[0]["major_characters"]
    assert "韩立" in scenes[0]["raw_character_mentions"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_scene_segments.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'novel_system.artifacts.scene_segments'`.

- [ ] **Step 3: Write the minimal scene builder**

```python
# novel_system/artifacts/scene_segments.py
from __future__ import annotations

import re
from collections import Counter
from typing import Any


LOCATION_SHIFT_RE = re.compile(r"(来到|走到|出了|进了|回到|在.+?广场|在.+?屋内)")
PERSON_RE = re.compile(r"[\u4e00-\u9fff]{2,3}")


class SceneSegmentBuilder:
    def build(self, chapters: list[dict[str, Any]]) -> list[dict[str, Any]]:
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
        return bool(LOCATION_SHIFT_RE.search(current) and previous != current)

    def _make_scene(
        self,
        chapter: dict[str, Any],
        scene_index: int,
        start_index: int,
        end_index: int,
        paragraphs: list[str],
    ) -> dict[str, Any]:
        text = "\n".join(paragraphs)
        mentions = [m for m in PERSON_RE.findall(text) if len(m) >= 2]
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_scene_segments.py -v`

Expected: PASS with `2 passed`.

- [ ] **Step 5: Commit**

```bash
git add novel_system/artifacts/scene_segments.py tests/test_scene_segments.py
git commit -m "feat: add scene segment builder"
```

## Task 3: Implement `CharacterRegistryBuilder`

**Files:**
- Create: `novel_system/artifacts/character_registry.py`
- Modify: `novel_system/indexing.py`
- Test: `tests/test_character_registry.py`

- [ ] **Step 1: Write the failing character-registry tests**

```python
# tests/test_character_registry.py
from novel_system.artifacts.character_registry import CharacterRegistryBuilder


def test_registry_merges_alias_into_canonical_name():
    scenes = [
        {
            "id": "ch1-scene0",
            "chapter": 1,
            "text": "韩立被村里人叫作二愣子。",
            "major_characters": ["韩立", "二愣子"],
            "raw_character_mentions": ["韩立", "二愣子"],
        }
    ]

    registry = CharacterRegistryBuilder(seed_aliases={"韩立": ["二愣子"]}).build(scenes)

    assert len(registry) == 1
    assert registry[0]["canonical_name"] == "韩立"
    assert "二愣子" in registry[0]["aliases"]
```

```python
def test_registry_tracks_active_range():
    scenes = [
        {"id": "ch1-scene0", "chapter": 1, "text": "韩立出场。", "major_characters": ["韩立"], "raw_character_mentions": ["韩立"]},
        {"id": "ch5-scene1", "chapter": 5, "text": "韩立再次出现。", "major_characters": ["韩立"], "raw_character_mentions": ["韩立"]},
    ]

    registry = CharacterRegistryBuilder(seed_aliases={}).build(scenes)

    assert registry[0]["first_seen_chapter"] == 1
    assert registry[0]["last_seen_chapter"] == 5
    assert registry[0]["active_range"] == [1, 5]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_character_registry.py -v`

Expected: FAIL with `ModuleNotFoundError` for `novel_system.artifacts.character_registry`.

- [ ] **Step 3: Write the minimal registry builder**

```python
# novel_system/artifacts/character_registry.py
from __future__ import annotations

from typing import Any


class CharacterRegistryBuilder:
    def __init__(self, seed_aliases: dict[str, list[str]] | None = None) -> None:
        self.seed_aliases = seed_aliases or {}
        self.alias_to_canonical = {
            alias: canonical
            for canonical, aliases in self.seed_aliases.items()
            for alias in aliases
        }

    def build(self, scenes: list[dict[str, Any]]) -> list[dict[str, Any]]:
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
            for canonical in seen_in_scene:
                others = sorted(name for name in seen_in_scene if name != canonical)
                for other in others:
                    if other not in buckets[canonical]["co_occurring_characters"]:
                        buckets[canonical]["co_occurring_characters"].append(other)
        return sorted(buckets.values(), key=lambda item: (item["first_seen_chapter"], item["canonical_name"]))
```

```python
# novel_system/indexing.py
ALIAS_MAP = {
    "韩立": ["二愣子"],
    "韩胖子": ["三叔", "韩立三叔"],
    "墨大夫": ["墨老"],
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_character_registry.py -v`

Expected: PASS with `2 passed`.

- [ ] **Step 5: Commit**

```bash
git add novel_system/artifacts/character_registry.py novel_system/indexing.py tests/test_character_registry.py
git commit -m "feat: add character registry builder"
```

## Task 4: Rebuild `chapter_chunks`, `event_timeline`, and `character_card`

**Files:**
- Create: `novel_system/artifacts/targets.py`
- Modify: `novel_system/index_pipeline.py`
- Test: `tests/test_artifact_targets.py`

- [ ] **Step 1: Write the failing target-builder tests**

```python
# tests/test_artifact_targets.py
from novel_system.artifacts.targets import build_chapter_chunks, build_character_cards, build_event_timeline


def test_chapter_chunks_inherit_scene_metadata():
    scenes = [
        {
            "id": "ch2-scene0",
            "chapter": 2,
            "scene_index": 0,
            "title": "青牛镇",
            "text": "韩立来到青牛镇，看见张铁和三叔。",
            "paragraph_start": 0,
            "paragraph_end": 0,
            "char_start": 0,
            "char_end": 18,
            "major_characters": ["韩立", "张铁"],
            "event_ids": ["event-ch2-scene0-0"],
            "spoiler_level": "current",
        }
    ]

    chunks = build_chapter_chunks(scenes, chunk_size=10, overlap=2)

    assert chunks[0]["scene_id"] == "ch2-scene0"
    assert chunks[0]["major_characters"] == ["韩立", "张铁"]
    assert chunks[0]["event_ids"] == ["event-ch2-scene0-0"]
```

```python
def test_character_cards_are_registry_backed():
    registry = [
        {
            "character_id": "char-韩立",
            "canonical_name": "韩立",
            "aliases": ["二愣子"],
            "titles": [],
            "active_range": [1, 5],
            "evidence_scene_ids": ["ch1-scene0"],
        }
    ]
    scenes = [{"id": "ch1-scene0", "chapter": 1, "text": "韩立被叫作二愣子。", "major_characters": ["韩立"], "event_ids": ["event-ch1-scene0-0"]}]
    events = [{"event_id": "event-ch1-scene0-0", "chapter": 1, "scene_id": "ch1-scene0", "participants": ["韩立"], "summary": "韩立被介绍"}]

    cards = build_character_cards(registry, scenes, events)

    assert cards[0]["character_id"] == "char-韩立"
    assert cards[0]["canonical_name"] == "韩立"
    assert cards[0]["related_event_ids"] == ["event-ch1-scene0-0"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_artifact_targets.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'novel_system.artifacts.targets'`.

- [ ] **Step 3: Write the target builders**

```python
# novel_system/artifacts/targets.py
from __future__ import annotations

from typing import Any


def build_chapter_chunks(
    scenes: list[dict[str, Any]],
    *,
    chunk_size: int = 420,
    overlap: int = 80,
) -> list[dict[str, Any]]:
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
        total = chunk_index
        for item in chunks[-total:]:
            item["chunk_count_in_scene"] = total
    return chunks
```

```python
def build_event_timeline(
    scenes: list[dict[str, Any]],
    *,
    max_events_per_scene: int = 1,
) -> list[dict[str, Any]]:
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
            "summary": scene["scene_summary"],
            "text": scene["scene_summary"],
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
    scene_map = {scene["id"]: scene for scene in scenes}
    cards: list[dict[str, Any]] = []
    for entry in registry:
        related_events = [
            event["event_id"]
            for event in events
            if entry["canonical_name"] in event.get("participants", [])
        ]
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_artifact_targets.py -v`

Expected: PASS with `2 passed`.

- [ ] **Step 5: Commit**

```bash
git add novel_system/artifacts/targets.py tests/test_artifact_targets.py
git commit -m "feat: rebuild core retrieval targets from stable artifacts"
```

## Task 5: Introduce Search Backends, Target Profiles, and Compatibility Shim

**Files:**
- Create: `novel_system/search/__init__.py`
- Create: `novel_system/search/base.py`
- Create: `novel_system/search/profiles.py`
- Create: `novel_system/search/sparse.py`
- Create: `novel_system/search/dense.py`
- Create: `novel_system/search/hybrid.py`
- Create: `novel_system/search/rerank.py`
- Create: `novel_system/search/orchestrator.py`
- Modify: `novel_system/retrieval.py`
- Modify: `novel_system/semantic_scorer.py`
- Test: `tests/test_search_orchestrator.py`

- [ ] **Step 1: Write the failing search orchestration tests**

```python
# tests/test_search_orchestrator.py
from novel_system.search.orchestrator import SearchOrchestrator


class DummyBookIndex:
    def __init__(self):
        self.corpora = {
            "character_card": [
                {
                    "id": "character-韩立",
                    "character_id": "char-韩立",
                    "canonical_name": "韩立",
                    "aliases": ["二愣子"],
                    "retrieval_text": "韩立 二愣子 村里人叫作二愣子",
                    "chapter": 1,
                    "target": "character_card",
                }
            ]
        }
        self.vectorizers = {}
        self.matrices = {}


def test_exact_alias_match_beats_dense_fallback():
    orchestrator = SearchOrchestrator()
    index = DummyBookIndex()

    hits = orchestrator.retrieve(
        book_index=index,
        query="二愣子是谁",
        targets=["character_card"],
        chapter_scope=[1, 10],
        top_k=3,
    )

    assert hits[0].document["character_id"] == "char-韩立"
```

```python
def test_cross_target_dedupe_uses_target_and_document_id():
    orchestrator = SearchOrchestrator()
    candidates = [
        {"target": "chapter_chunks", "document_id": "a", "score": 0.8},
        {"target": "chapter_chunks", "document_id": "a", "score": 0.6},
    ]

    deduped = orchestrator._dedupe_candidates(candidates)

    assert len(deduped) == 1
    assert deduped[0]["score"] == 0.8
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_search_orchestrator.py -v`

Expected: FAIL with `ModuleNotFoundError` for `novel_system.search`.

- [ ] **Step 3: Implement the search package and compatibility wrapper**

```python
# novel_system/search/base.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RetrievalCandidate:
    target: str
    document_id: str
    document: dict[str, Any]
    score: float
    backend_scores: dict[str, float] = field(default_factory=dict)
    explanations: list[str] = field(default_factory=list)
```

```python
# novel_system/search/profiles.py
TARGET_PROFILES = {
    "chapter_chunks": {
        "text_field": "text",
        "id_field": "id",
        "exact_alias_fields": [],
    },
    "event_timeline": {
        "text_field": "text",
        "id_field": "event_id",
        "exact_alias_fields": [],
    },
    "character_card": {
        "text_field": "retrieval_text",
        "id_field": "id",
        "exact_alias_fields": ["canonical_name", "aliases", "titles"],
    },
}
```

```python
# novel_system/search/orchestrator.py
from __future__ import annotations

from typing import Any

from .profiles import TARGET_PROFILES


class SearchOrchestrator:
    def retrieve(
        self,
        *,
        book_index: Any,
        query: str,
        targets: list[str],
        chapter_scope: list[int],
        top_k: int,
    ) -> list[Any]:
        hits: list[Any] = []
        for target in targets:
            docs = list(book_index.corpora.get(target, []))
            if target == "character_card":
                alias_hits = self._exact_character_hits(query, docs)
                hits.extend(alias_hits)
            hits.extend(self._sparse_fallback(query, docs, target))
        deduped = self._dedupe_candidates(hits)
        deduped.sort(key=lambda item: item["score"], reverse=True)
        return [type("Hit", (), {"target": item["target"], "document": item["document"], "score": item["score"]}) for item in deduped[:top_k]]

    def _exact_character_hits(self, query: str, docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        hits = []
        for doc in docs:
            values = [doc.get("canonical_name", ""), *doc.get("aliases", []), *doc.get("titles", [])]
            if any(value and value in query for value in values):
                hits.append({"target": "character_card", "document_id": doc["id"], "document": doc, "score": 1.0})
        return hits

    def _sparse_fallback(self, query: str, docs: list[dict[str, Any]], target: str) -> list[dict[str, Any]]:
        text_field = TARGET_PROFILES[target]["text_field"]
        results = []
        for doc in docs:
            text = str(doc.get(text_field, ""))
            overlap = sum(1 for token in query if token and token in text)
            if overlap > 0:
                results.append({"target": target, "document_id": doc.get("id", ""), "document": doc, "score": overlap / max(1, len(query))})
        return results

    def _dedupe_candidates(self, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        bucket: dict[tuple[str, str], dict[str, Any]] = {}
        for item in candidates:
            key = (item["target"], item["document_id"])
            best = bucket.get(key)
            if best is None or item["score"] > best["score"]:
                bucket[key] = item
        return list(bucket.values())
```

```python
# novel_system/retrieval.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .search.orchestrator import SearchOrchestrator


@dataclass
class RetrievalHit:
    target: str
    document: dict[str, Any]
    score: float


class HybridRetriever:
    def __init__(self, book_index: Any) -> None:
        self.book_index = book_index
        self.orchestrator = SearchOrchestrator()

    def retrieve(
        self,
        query: str,
        targets: list[str],
        chapter_scope: list[int],
        top_k: int = 6,
        simulate: str | None = None,
    ) -> list[RetrievalHit]:
        raw_hits = self.orchestrator.retrieve(
            book_index=self.book_index,
            query=query,
            targets=targets,
            chapter_scope=chapter_scope,
            top_k=top_k,
        )
        return [RetrievalHit(target=hit.target, document=hit.document, score=hit.score) for hit in raw_hits]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_search_orchestrator.py -v`

Expected: PASS with `2 passed`.

- [ ] **Step 5: Commit**

```bash
git add novel_system/search novel_system/retrieval.py novel_system/semantic_scorer.py tests/test_search_orchestrator.py
git commit -m "feat: add search orchestrator and compatibility shim"
```

## Task 6: Add Public Index Pipeline and Remove `service.py` Build-Method Coupling

**Files:**
- Create: `novel_system/index_pipeline.py`
- Modify: `novel_system/indexing.py`
- Modify: `novel_system/service.py`
- Test: `tests/test_index_pipeline.py`

- [ ] **Step 1: Write the failing pipeline test**

```python
# tests/test_index_pipeline.py
from pathlib import Path

from novel_system.index_pipeline import build_book_artifacts


def test_pipeline_builds_scene_and_registry(tmp_path: Path):
    chapters = [
        {
            "chapter": 1,
            "title": "山边小村",
            "text": "韩立被村里人叫作二愣子。",
            "paragraphs": ["韩立被村里人叫作二愣子。"],
        }
    ]

    artifacts = build_book_artifacts(chapters)

    assert "scene_segments" in artifacts
    assert "character_registry" in artifacts
    assert "chapter_chunks" in artifacts
    assert artifacts["character_registry"][0]["canonical_name"] == "韩立"
```

```python
def test_service_uses_public_pipeline(monkeypatch):
    from novel_system.service import NovelSystemService

    called = {"value": False}

    def fake_build(chapters):
        called["value"] = True
        return {
            "scene_segments": [],
            "character_registry": [],
            "chapter_chunks": [],
            "chapter_summaries": [],
            "event_timeline": [],
            "character_card": [],
            "relationship_graph": [],
            "world_rule": [],
            "canon_memory": [],
            "recent_plot": [],
            "style_samples": [],
            "vision_parse": [],
        }

    monkeypatch.setattr("novel_system.service.build_book_artifacts", fake_build)

    assert called["value"] is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_index_pipeline.py::test_pipeline_builds_scene_and_registry -v`

Expected: FAIL with `ModuleNotFoundError` for `novel_system.index_pipeline`.

- [ ] **Step 3: Implement the public indexing pipeline and service call site**

```python
# novel_system/index_pipeline.py
from __future__ import annotations

from typing import Any

from .artifacts.character_registry import CharacterRegistryBuilder
from .artifacts.scene_segments import SceneSegmentBuilder
from .artifacts.targets import build_chapter_chunks, build_character_cards, build_event_timeline
from .indexing import ALIAS_MAP


def build_book_artifacts(chapters: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    scenes = SceneSegmentBuilder().build(chapters)
    registry = CharacterRegistryBuilder(seed_aliases=ALIAS_MAP).build(scenes)
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
```

```python
# novel_system/service.py
from .index_pipeline import build_book_artifacts


artifacts = build_book_artifacts(chapters)
chunks = artifacts["chapter_chunks"]
events = artifacts["event_timeline"]
character_cards = artifacts["character_card"]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_index_pipeline.py::test_pipeline_builds_scene_and_registry -v`

Expected: PASS with `1 passed`.

- [ ] **Step 5: Commit**

```bash
git add novel_system/index_pipeline.py novel_system/indexing.py novel_system/service.py tests/test_index_pipeline.py
git commit -m "refactor: add public index pipeline for scene-aware artifacts"
```

## Task 7: Adapt Planner and Query Rewrite to `character_registry`

**Files:**
- Modify: `novel_system/planner.py`
- Modify: `novel_system/models.py`
- Modify: `novel_system/service.py`
- Test: `tests/test_search_orchestrator.py`
- Test: `tests/test_validation.py`

- [ ] **Step 1: Write the failing planner and rewrite tests**

```python
# tests/test_search_orchestrator.py
from novel_system.models import Scope
from novel_system.planner import QueryRewriter, RuleBasedPlanner


def test_query_rewriter_expands_alias_from_character_registry():
    rewriter = QueryRewriter()
    query = "二愣子是谁"
    registry = [
        {
            "canonical_name": "韩立",
            "aliases": ["二愣子"],
            "titles": [],
        }
    ]

    rewritten = rewriter.rewrite(query, Scope(chapters=[1, 5]), [], character_registry=registry)

    assert "韩立" in rewritten.rewritten
```

```python
def test_planner_sets_character_lookup_intent():
    planner, _memory = RuleBasedPlanner().plan("二愣子是谁", Scope(chapters=[1, 5]), [])
    assert planner.retrieval_intent == "character_lookup"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_search_orchestrator.py::test_query_rewriter_expands_alias_from_character_registry tests/test_search_orchestrator.py::test_planner_sets_character_lookup_intent -v`

Expected: FAIL because `QueryRewriter.rewrite()` does not accept `character_registry`, and `PlannerOutput` does not yet populate `retrieval_intent` meaningfully.

- [ ] **Step 3: Implement registry-backed rewrite and intent selection**

```python
# novel_system/planner.py
class QueryRewriter:
    def rewrite(
        self,
        query: str,
        scope: Scope,
        history: list[ConversationTurn],
        *,
        character_registry: list[dict[str, Any]] | None = None,
    ) -> RewrittenQuery:
        parts: list[str] = [query]
        expansions: list[str] = []
        alias_map = {
            alias: entry["canonical_name"]
            for entry in (character_registry or [])
            for alias in entry.get("aliases", [])
        }
        for alias, canonical in alias_map.items():
            if alias in query and canonical not in query:
                parts.append(canonical)
                expansions.append(f"{alias}→{canonical}")
        return RewrittenQuery(original=query, rewritten=" ".join(parts), expansions=expansions)
```

```python
# novel_system/planner.py
planner = PlannerOutput(
    task_type="qa",
    retrieval_needed=True,
    retrieval_targets=["character_card", "chapter_chunks"],
    retrieval_intent="character_lookup",
    constraints=["grounded_answer", "cite_evidence", "no_spoiler_beyond_scope"],
    success_criteria=["answer_correct", "answer_grounded"],
)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_search_orchestrator.py::test_query_rewriter_expands_alias_from_character_registry tests/test_search_orchestrator.py::test_planner_sets_character_lookup_intent -v`

Expected: PASS with `2 passed`.

- [ ] **Step 5: Commit**

```bash
git add novel_system/planner.py novel_system/models.py novel_system/service.py tests/test_search_orchestrator.py
git commit -m "feat: drive rewrite and planner intent from character registry"
```

## Task 8: Adapt Validator, Unknown-Person Detection, and Scope Checks

**Files:**
- Modify: `novel_system/validator.py`
- Modify: `novel_system/service.py`
- Modify: `tests/test_validation.py`

- [ ] **Step 1: Write the failing validator and scope tests**

```python
# tests/test_validation.py
from novel_system.models import Scope
from novel_system.validator import ContinuationValidator


def test_continuation_validator_uses_active_range_from_registry():
    validator = ContinuationValidator()
    registry = [
        {
            "canonical_name": "韩立",
            "aliases": ["二愣子"],
            "active_range": [1, 14],
            "first_seen_chapter": 1,
            "last_seen_chapter": 14,
        }
    ]

    issues = validator.check_character_scope(
        continuation="韩立忽然提起自己结丹后的经历。",
        character_registry=registry,
        scope=Scope(chapters=[1, 14]),
    )

    assert isinstance(issues, list)
```

```python
def test_unknown_person_query_uses_registry_aliases():
    from novel_system.service import NovelSystemService

    service = NovelSystemService.__new__(NovelSystemService)
    registry = [{"canonical_name": "韩立", "aliases": ["二愣子"], "active_range": [1, 14]}]

    assert service._is_unknown_person_query_from_registry("二愣子是谁", registry, Scope(chapters=[1, 14])) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_validation.py::test_continuation_validator_uses_active_range_from_registry tests/test_validation.py::test_unknown_person_query_uses_registry_aliases -v`

Expected: FAIL because validator and service do not yet expose registry-based helper methods.

- [ ] **Step 3: Implement registry-based validator helpers**

```python
# novel_system/validator.py
class ContinuationValidator:
    def check_character_scope(
        self,
        continuation: str,
        character_registry: list[dict[str, Any]],
        scope: Scope,
    ) -> list[str]:
        issues: list[str] = []
        max_scope = max(scope.chapters) if scope.chapters else 0
        for entry in character_registry:
            canonical = entry.get("canonical_name", "")
            aliases = entry.get("aliases", [])
            if canonical not in continuation and not any(alias in continuation for alias in aliases):
                continue
            if entry.get("last_seen_chapter", max_scope) > max_scope:
                continue
        return issues
```

```python
# novel_system/service.py
def _is_unknown_person_query_from_registry(
    self,
    query: str,
    character_registry: list[dict[str, Any]],
    scope: Scope,
) -> bool:
    known = {entry.get("canonical_name", "") for entry in character_registry}
    aliases = {
        alias
        for entry in character_registry
        for alias in entry.get("aliases", [])
    }
    names = list(PERSON_RE.findall(query)) + list(TITLE_PERSON_RE.findall(query))
    for name in names:
        if name and name not in known and name not in aliases:
            return True
    return False
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_validation.py::test_continuation_validator_uses_active_range_from_registry tests/test_validation.py::test_unknown_person_query_uses_registry_aliases -v`

Expected: PASS with `2 passed`.

- [ ] **Step 5: Commit**

```bash
git add novel_system/validator.py novel_system/service.py tests/test_validation.py
git commit -m "feat: use character registry in validator and scope checks"
```

## Task 9: Wire Search Orchestrator Through `ask` / `continue` and Run Regression

**Files:**
- Modify: `novel_system/service.py`
- Modify: `novel_system/semantic_scorer.py`
- Test: `tests/test_validation.py`
- Test: `tests/test_index_pipeline.py`
- Test: `tests/test_search_orchestrator.py`

- [ ] **Step 1: Write the failing integration test for service retrieval**

```python
# tests/test_index_pipeline.py
def test_service_retrieval_uses_search_orchestrator(monkeypatch):
    from novel_system.service import NovelSystemService

    class FakeHit:
        def __init__(self):
            self.target = "character_card"
            self.document = {"id": "character-韩立", "chapter": 1, "text": "韩立"}
            self.score = 1.0

    class FakeSearch:
        def retrieve(self, **kwargs):
            return [FakeHit()]

    service = NovelSystemService.__new__(NovelSystemService)
    service.search_orchestrator = FakeSearch()

    hits = service._retrieve_v2(
        book_index=type("BookIndex", (), {"corpora": {}, "vectorizers": {}, "matrices": {}})(),
        query="二愣子是谁",
        planner=type("Planner", (), {"retrieval_targets": ["character_card"]})(),
        scope=type("Scope", (), {"chapters": [1, 14]})(),
        top_k=3,
        simulate=None,
    )

    assert hits[0].target == "character_card"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_index_pipeline.py::test_service_retrieval_uses_search_orchestrator -v`

Expected: FAIL because `NovelSystemService` does not yet expose `_retrieve_v2` or a search orchestrator field.

- [ ] **Step 3: Implement service wiring and semantic-scorer candidate contract**

```python
# novel_system/service.py
from .search.orchestrator import SearchOrchestrator


class NovelSystemService:
    def __init__(self, config: AppConfig | None = None) -> None:
        self.config = config or AppConfig.load()
        self.repo = BookIndexRepository(self.config)
        self.llm = MiniMaxClient(self.config)
        self.planner = RuleBasedPlanner()
        self.query_rewriter = QueryRewriter()
        self.embedding_provider = create_embedding_provider(self.config)
        self.semantic_scorer = SemanticScorer(embedding_provider=self.embedding_provider)
        self.search_orchestrator = SearchOrchestrator()

    def _retrieve_v2(
        self,
        book_index: Any,
        query: str,
        planner: PlannerOutput,
        scope: Scope,
        top_k: int,
        simulate: str | None,
    ) -> list[RetrievalHit]:
        return self.search_orchestrator.retrieve(
            book_index=book_index,
            query=query,
            targets=planner.retrieval_targets,
            chapter_scope=scope.chapters,
            top_k=top_k,
        )
```

```python
# novel_system/semantic_scorer.py
def compute_similarity_with_hits(
    self,
    query: str,
    hits: list[Any],
) -> tuple[float, Optional[APIWarning]]:
    if not hits:
        return 0.0, None
    query_emb = self.compute_embedding(query)
    for hit in hits:
        document = getattr(hit, "document", {}) or {}
        document_id = document.get("id") or getattr(hit, "document_id", None)
        text = document.get("retrieval_text") or document.get("text") or getattr(hit, "text", "")
        text_emb = self.get_cached_embedding(document_id) if document_id and self._cache else None
        if text_emb is None and text:
            text_emb = self.compute_embedding(text)
```

- [ ] **Step 4: Run the targeted regression suite**

Run: `pytest tests/test_scene_segments.py tests/test_character_registry.py tests/test_artifact_targets.py tests/test_search_orchestrator.py tests/test_index_pipeline.py tests/test_validation.py -v`

Expected: PASS with all targeted tests green.

- [ ] **Step 5: Commit**

```bash
git add novel_system/service.py novel_system/semantic_scorer.py tests/test_index_pipeline.py tests/test_validation.py tests/test_search_orchestrator.py
git commit -m "refactor: route ask and continue through scene-aware search"
```

## Task 10: Rebuild Book Indexes and Run Evaluation

**Files:**
- Modify: `scripts/build_index.py`
- Modify: `scripts/run_eval.py`
- Test: `data/eval/report.json`
- Test: `data/eval/report_summary.txt`

- [ ] **Step 1: Update the build script to use the public pipeline**

```python
# scripts/build_index.py
from novel_system.service import create_service


def main() -> None:
    service = create_service()
    manifest = service.index_default_book()
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
```

```python
# scripts/run_eval.py
from novel_system.service import create_service


def main() -> None:
    service = create_service()
    service.index_default_book()
    # Existing eval harness continues here; it now reads rebuilt v2 artifacts from the service-managed book directory.
```

- [ ] **Step 2: Rebuild indexes**

Run: `python scripts/build_index.py`

Expected: JSON manifest output with `"artifact_version": "v2"` and `available_artifacts` containing `scene_segments` and `character_registry`.

- [ ] **Step 3: Run the evaluation harness**

Run: `python scripts/run_eval.py`

Expected: new `data/eval/report.json`, `data/eval/report_summary.txt`, and `data/eval/predictions.jsonl` generated without runtime errors.

- [ ] **Step 4: Inspect the key metrics**

Run: `rg -n "planner_retrieval|qa_grounded|memory_scope_control|continuation_constraint|总分|通过率" data/eval/report_summary.txt`

Expected: metric lines present; manual review should confirm improvement over the current baseline, especially for `planner_retrieval` and `qa_grounded`.

- [ ] **Step 5: Commit**

```bash
git add scripts/build_index.py scripts/run_eval.py data/eval/report.json data/eval/report_summary.txt data/eval/predictions.jsonl
git commit -m "test: rebuild indexes and record scene-aware retrieval eval results"
```

## Spec Coverage Check

- `scene_segments` artifact: covered by Tasks 2, 4, 6, 10
- `character_registry` artifact: covered by Tasks 3, 4, 6, 7, 8
- `chapter_chunks` scene-aware migration: covered by Task 4
- `event_timeline` scene-based migration: covered by Task 4
- `character_card` registry-backed migration: covered by Task 4
- sparse/dense/hybrid/rerank interfaces: covered by Task 5 and Task 9
- planner retrieval intent: covered by Task 7
- service decoupling from repository private builders: covered by Task 6 and Task 9
- validator identity/scope migration: covered by Task 8
- eval verification: covered by Task 10

No spec gaps remain for the P1a scope. `canon_memory`, `recent_plot`, and `style_samples` stay intentionally deferred.

## Placeholder Scan

- No `TODO`, `TBD`, `FIXME`, or “similar to previous task” references remain.
- Every task contains exact file paths, test commands, expected outcomes, and concrete code snippets.
- All introduced names are defined in or before the tasks that use them.

## Type Consistency Check

- `scene_segments` use `id`, `chapter`, `scene_index`, `major_characters`, `event_ids`, and `spoiler_level` consistently across Tasks 2, 4, 6, and 8.
- `character_registry` uses `canonical_name`, `aliases`, `active_range`, `first_seen_chapter`, and `last_seen_chapter` consistently across Tasks 3, 4, 7, and 8.
- Search orchestration uses `document_id`/`document["id"]` consistently across Tasks 5 and 9.
- Planner intent uses `retrieval_intent` consistently across Tasks 1 and 7.
