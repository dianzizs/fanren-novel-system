# Scene-Aware Retrieval Redesign

## Goal

Rebuild retrieval around stable intermediate artifacts and explicit retrieval stages so the system can answer grounded questions, resolve character identity consistently, and support spoiler-aware continuation without keeping all logic inside one file.

This redesign introduces two new first-class artifacts:

1. `scene_segments`: the canonical narrative segmentation layer between chapters and retrieval chunks
2. `character_registry`: the canonical identity layer shared by query rewrite, retrieval, validator, and graph/timeline features

The immediate implementation target is to stabilize three retrieval targets first:

- `chapter_chunks`
- `event_timeline`
- `character_card`

Only after those three are stable should `canon_memory`, `recent_plot`, and `style_samples` be migrated onto the new framework.

## Why This Change

The current system has four structural problems:

1. `chapter_chunks` are built by raw character-window slicing, so retrieval units do not align with narrative scenes or event boundaries.
2. Identity knowledge is fragmented across `indexing.py`, `planner.py`, `entity_extractor.py`, and `service.py`, causing alias mismatch and inconsistent unknown-person handling.
3. `retrieval.py` is acting as both target router and search engine, but it only performs sparse TF-IDF search and target merging; there is no real sparse/dense/hybrid/rerank pipeline.
4. `service.py` directly calls repository private build methods and depends on unstable artifact schemas, which makes retrieval redesign harder than it should be.

These issues line up with the current evaluation failures in planner retrieval and grounded QA. The redesign therefore focuses on retrieval correctness before adding more target types.

## Scope

### In Scope

- Introduce `scene_segments` artifact
- Introduce `character_registry` artifact
- Rebuild `chapter_chunks`, `event_timeline`, and `character_card` on top of those artifacts
- Split retrieval into sparse, dense, hybrid, and rerank stages behind explicit interfaces
- Update planner and service to use retrieval intent and target profiles instead of hard-coded target lists only
- Update validator and rewrite logic to read shared canonical character data
- Preserve current public APIs where feasible while changing internal artifact generation and retrieval orchestration

### Out of Scope

- Full knowledge graph redesign
- Rich structured extraction for all character attributes on day one
- A full rewrite of all artifact builders in the same pass
- UI changes beyond compatibility work required by new schemas

## Design Principles

1. Artifact schema must stabilize before retrieval policy.
2. Identity resolution must have one source of truth.
3. Search backends must be pluggable per target.
4. Display schema and retrieval schema must not be forced to be identical.
5. Service orchestration should depend on public builders and repositories, not private helper methods.
6. Migration should preserve backward compatibility where the current API expects existing target names.

## Target Architecture

The redesigned indexing and retrieval stack is:

`chapters -> scene_segments -> character_registry -> target builders -> target indexes -> retrieval orchestrator -> service/planner/validator consumers`

The main architectural layers are:

1. **Parsing and segmentation**
   - Parse chapters from raw text
   - Segment chapters into scenes
   - Attach scene-local narrative metadata

2. **Canonical identity**
   - Aggregate mentions into canonical character entries
   - Normalize aliases, titles, and active ranges

3. **Artifact building**
   - Build retrieval targets from stable intermediate artifacts
   - Keep target-specific retrieval text separate from display fields

4. **Indexing**
   - Build sparse index and dense embedding data per target
   - Store enough metadata for filtering and rerank

5. **Retrieval**
   - Perform target-local retrieval through explicit backends
   - Fuse, dedupe, and rerank across targets

6. **Consumption**
   - Planner chooses retrieval intent
   - Service invokes orchestrator
   - Validator and rewrite reuse shared canonical metadata

## New Artifact: `scene_segments`

### Purpose

`scene_segments` becomes the canonical narrative segmentation layer. It replaces the current assumption that chapter text can be sliced into fixed windows without losing semantic structure.

The artifact must represent a coherent local scene or sub-scene rather than an arbitrary text window. It is the bridge between raw chapter text and every retrieval target that depends on local context.

### Generation Strategy

Scene segmentation should start with rule-based heuristics rather than requiring an LLM:

1. Split chapter text into paragraphs
2. Detect strong scene boundaries using:
   - explicit time shifts
   - explicit location shifts
   - major participant set changes
   - dialogue/action density transitions
   - long paragraph distance or chapter-local structural markers
3. Merge tiny fragments when they do not form independent narrative units
4. Produce stable scene ids inside each chapter

The initial implementation should prefer conservative segmentation. Slightly oversized scenes are safer than over-fragmented scenes for retrieval.

### Required Schema

Each scene segment should contain:

- `id`: stable scene id, for example `ch12-scene3`
- `chapter`
- `scene_index`
- `title`
- `text`
- `paragraph_start`
- `paragraph_end`
- `char_start`
- `char_end`
- `scene_summary`
- `major_characters`: canonical names when available
- `raw_character_mentions`
- `event_ids`
- `spoiler_level`
- `prev_scene_id`
- `next_scene_id`

### Notes

- `major_characters` should reference canonical names from `character_registry` when possible.
- `spoiler_level` should be relative to chapter order, not a global semantic label. A simple initial scheme is `current`, `near_future`, `far_future`, where scene-derived targets inherit the scene level.

## New Artifact: `character_registry`

### Purpose

`character_registry` is the single source of truth for character identity. It exists so that query rewrite, retrieval, validator, and graph/timeline logic all resolve the same person the same way.

The first version is an identity registry, not a full biography database.

### Generation Strategy

Build the registry offline from chapter text and scene data:

1. Extract person-like mentions and title-bearing mentions
2. Normalize obvious aliases and known forms
3. Cluster mentions into canonical identities using:
   - exact name equality
   - configured alias mappings
   - title/name co-occurrence
   - chapter overlap and scene co-reference heuristics
4. Record active range and evidence scenes

The first pass can remain heuristic and should expose confidence so downstream consumers can be cautious.

### Required Schema

Each registry entry should contain:

- `character_id`
- `canonical_name`
- `aliases`
- `titles`
- `name_variants`
- `first_seen_chapter`
- `last_seen_chapter`
- `active_range`
- `evidence_scene_ids`
- `co_occurring_characters`
- `confidence`

### Shared Usage

This artifact is used by:

- query rewrite alias expansion
- character-card retrieval
- unknown-person detection
- validator character presence and scope checks
- graph and timeline participant normalization

No other module should keep its own long-lived alias table once this registry is introduced. Small bootstrapping seed maps may still exist, but they should feed the registry builder rather than bypass it.

## Rebuilt Target: `chapter_chunks`

### Purpose

`chapter_chunks` remain the primary fine-grained evidence target for QA, but they are rebuilt as scene-aware chunks rather than raw chapter windows.

### Build Strategy

1. Iterate through `scene_segments`
2. Split only within a scene when a scene is too long
3. Carry scene metadata into each chunk

This keeps retrieval granular enough for evidence extraction while preserving scene coherence.

### Required Schema

- `id`
- `chapter`
- `title`
- `target`
- `text`
- `source`
- `scene_id`
- `scene_index`
- `chunk_index_in_scene`
- `chunk_count_in_scene`
- `major_characters`
- `event_ids`
- `spoiler_level`
- `paragraph_start`
- `paragraph_end`
- `char_start`
- `char_end`

### Retrieval Role

`chapter_chunks` should default to hybrid retrieval with scene-aware rerank. It is the main target for grounded evidence and quote extraction.

## Rebuilt Target: `event_timeline`

### Purpose

`event_timeline` should become event-centric rather than chapter-centric. The current one-event-per-chapter structure is too coarse to answer causal or scope-sensitive questions.

### Build Strategy

1. Start from `scene_segments`
2. Extract zero, one, or multiple events per scene
3. Normalize participants through `character_registry`
4. Link neighboring events when ordering is obvious

### Required Schema

- `event_id`
- `chapter`
- `scene_id`
- `title`
- `target`
- `summary`
- `text`
- `participants`
- `location`
- `event_type`
- `preceding_event_ids`
- `following_event_ids`
- `spoiler_level`
- `source`

### Retrieval Role

`event_timeline` should favor sparse matching for event names, actions, and participants, with dense retrieval as recall support and rerank based on participant overlap and chapter scope.

## Rebuilt Target: `character_card`

### Purpose

`character_card` becomes a registry-backed profile target rather than a frequency-ranked name summary. This makes character retrieval stable and keeps alias resolution consistent.

### Build Strategy

1. Start from `character_registry`
2. Aggregate high-signal scenes and events for each character
3. Build both:
   - display-friendly fields
   - retrieval-friendly text

### Required Schema

- `id`
- `character_id`
- `canonical_name`
- `aliases`
- `titles`
- `chapter`
- `chapter_span`
- `active_range`
- `target`
- `summary`
- `retrieval_text`
- `key_scene_ids`
- `related_event_ids`
- `source`

### Retrieval Role

`character_card` should prioritize exact canonical-name hits and alias/title expansion before falling back to sparse and dense similarity. For character lookup, identity precision matters more than broad semantic similarity.

## Retrieval Layer Redesign

### Problem with the Current Structure

The current `HybridRetriever` is a target loop wrapped around sparse TF-IDF search. It does not expose backend interfaces, target-level policies, or reranking stages, which makes it difficult to tune by target type.

### New Retrieval Interfaces

Introduce the following interfaces:

- `RetrieverBackend`
  - `search(query, docs, index, filters, top_k) -> list[RetrievalCandidate]`
- `SparseRetriever`
- `DenseRetriever`
- `HybridRetriever`
- `Reranker`

`RetrievalCandidate` should carry:

- `target`
- `document_id`
- `document`
- `backend_scores`
- `score`
- `explanations`

### Target Profiles

Each retrieval target should declare a `TargetProfile` with:

- target name
- searchable text fields
- filterable metadata
- default backend
- fusion weights
- dedupe key
- default `top_k`
- rerank policy

Example profile expectations:

- `chapter_chunks`: hybrid, rerank by scope proximity + identity overlap + scene density
- `event_timeline`: sparse-first hybrid, rerank by participant overlap + temporal relevance
- `character_card`: exact/alias + sparse, optional dense fallback, strict dedupe on `character_id`

### Retrieval Flow

The new retrieval flow should be:

1. Rewrite query using `character_registry`
2. Resolve retrieval intent from planner output
3. Select target profiles
4. Execute target-local retrieval
5. Apply target-local rerank
6. Fuse cross-target candidates
7. Dedupe and trim final results

### Dense Retrieval Notes

Dense retrieval must use the same document identity and text fields as the sparse layer. The current scorer/hit mismatch should be fixed by ensuring retrieval candidates always carry:

- document id
- retrieval text used for embedding
- any cached embedding key

This removes the current ambiguity around `chunk_id` versus `document["id"]`.

## Indexing Pipeline Redesign

### New Builder Structure

Replace the monolithic build flow with explicit builder components:

- `ChapterParser`
- `SceneSegmentBuilder`
- `CharacterRegistryBuilder`
- `ArtifactBuilderRegistry`
- `VectorIndexBuilder`

Each builder should expose a public method and a typed input/output contract. `service.py` should call these public builders instead of repository private helpers.

### Book Repository Responsibilities

`BookIndexRepository` should focus on:

- artifact persistence
- manifest management
- loading indexes and metadata

It should no longer be the main place where all artifact generation logic lives.

### Manifest Changes

Add artifact version metadata so the system can distinguish old and new indexes:

- `artifact_version`
- `available_artifacts`
- per-artifact counts
- indexing timestamps

This makes migration and rebuild decisions explicit.

## Planner Changes

### Current Problem

The planner currently emits target name lists directly. This ties high-level intent to low-level implementation details and makes retrieval tuning brittle.

### Proposed Change

Add a lightweight retrieval-intent layer. Planner output should continue exposing `retrieval_targets` for compatibility, but internally it should also carry a retrieval intent, such as:

- `scene_evidence`
- `event_lookup`
- `character_lookup`
- `timeline_reasoning`
- `continuation_context`

The service or retrieval orchestrator then maps intent to target profiles and backend policies.

### Benefits

- better explainability
- simpler tuning
- less planner churn when target composition changes

## Service Changes

### Current Problem

`service.py` currently:

- constructs retrieval behavior directly
- calls repository private build helpers
- embeds alias and graph canonicalization logic that belongs in shared artifacts

### Proposed Change

Refactor service responsibilities to:

- call indexing pipeline entrypoints
- call retrieval orchestrator
- format evidence for response models
- delegate identity resolution to `character_registry`

Specific changes:

1. Replace direct `_build_*` calls with an indexing pipeline entrypoint.
2. Replace direct `HybridRetriever` construction with retrieval orchestrator usage.
3. Move unknown-person detection to registry-backed logic.
4. Reuse registry canonical names for graph and timeline normalization.

## Validator Changes

### Current Problem

Validator logic assumes richer character-card fields than current artifact builders actually produce. This creates schema drift and hides failure behind optimistic tests.

### Proposed Change

Update validator to consume:

- `character_registry` for identity and activity range
- `chapter_chunks` and `scene_segments` for evidence locality
- `event_timeline` for spoiler and causality checks

The validator should stop assuming that every character card always carries full appearance/personality/level data. Those checks can remain optional when fields exist, but identity and scope checks must not depend on them.

### Immediate Validator Wins

- better unknown-person detection
- fewer alias-related false negatives
- cleaner spoiler checks using event ids and scene/chapter ranges

## Migration Strategy

### Phase P1a: Foundation

1. Add `scene_segments`
2. Add `character_registry`
3. Add artifact versioning
4. Introduce new builder interfaces

### Phase P1a: Core Target Migration

1. Rebuild `chapter_chunks`
2. Rebuild `event_timeline`
3. Rebuild `character_card`
4. Update sparse and dense indexing to match new retrieval text fields
5. Introduce retrieval orchestrator and target profiles

### Phase P1a: Consumer Migration

1. Adapt planner
2. Adapt service
3. Adapt validator
4. Adapt graph/timeline helper logic to canonical names

### Phase P1b: Secondary Targets

After the three core targets stabilize:

1. Rebuild `canon_memory` atop events and summaries
2. Rebuild `recent_plot` atop scene recency
3. Rebuild `style_samples` atop scene-level stylistic selection

This staged migration keeps the highest-risk retrieval surface focused first.

## Compatibility Plan

External compatibility should be preserved by:

- keeping existing public target names such as `chapter_chunks`, `event_timeline`, and `character_card`
- allowing old API response shapes where possible
- storing new artifact files alongside existing manifest-driven book directories

Internal compatibility should not prevent schema cleanup. If a consumer currently depends on unstable fields, it should be updated rather than forcing the new design to mimic broken assumptions.

## Testing Strategy

### Unit Tests

- scene segmentation boundaries
- character clustering and alias normalization
- target profile routing
- sparse/dense/hybrid/rerank scoring behavior
- manifest version and artifact catalog behavior

### Integration Tests

- end-to-end indexing builds new artifacts successfully
- planner intent maps to correct target profiles
- ask flow returns scene-grounded evidence
- continue flow respects canonical character scope
- validator reads new schemas correctly

### Regression and Eval Focus

Track these evaluation categories first:

- `planner_retrieval`
- `qa_grounded`
- `memory_scope_control`
- `continuation_constraint`

Success is defined as meaningful improvement over the current baseline, especially in grounded QA and target selection.

## Risks and Mitigations

### Risk 1: Scene segmentation is noisy

Mitigation:

- start heuristic and conservative
- preserve paragraph offsets so scene splits are debuggable
- allow later replacement of segmenter without changing downstream target contracts

### Risk 2: Character clustering merges the wrong people

Mitigation:

- keep confidence scores
- prefer under-merging to over-merging in v1
- allow seed alias maps and manual overrides

### Risk 3: Retrieval tuning becomes harder after abstraction

Mitigation:

- keep target profiles explicit and inspectable
- log backend scores and rerank reasons in trace output

### Risk 4: Migration touches too much code at once

Mitigation:

- split into P1a and P1b
- keep old target names
- gate new artifact version with clear rebuild path

## File and Module Plan

Expected new or reshaped modules:

- `novel_system/artifacts/scene_segments.py`
- `novel_system/artifacts/character_registry.py`
- `novel_system/artifacts/targets.py`
- `novel_system/retrieval/base.py`
- `novel_system/retrieval/backends/sparse.py`
- `novel_system/retrieval/backends/dense.py`
- `novel_system/retrieval/backends/hybrid.py`
- `novel_system/retrieval/rerank.py`
- `novel_system/retrieval/orchestrator.py`

Expected major modifications:

- `novel_system/indexing.py`
- `novel_system/service.py`
- `novel_system/planner.py`
- `novel_system/validator.py`
- tests covering indexing, retrieval, and validation

The exact file split can adapt to the existing repository style, but these boundaries should remain conceptually intact.

## Acceptance Criteria

The redesign is considered complete for P1a when:

1. indexing produces `scene_segments` and `character_registry`
2. `chapter_chunks`, `event_timeline`, and `character_card` are built from those artifacts
3. retrieval backends are separated behind explicit interfaces
4. service no longer calls repository private `_build_*` methods
5. rewrite, retrieval, and validator all resolve identities through the same canonical source
6. evaluation improves materially on retrieval-target selection and grounded QA

## Recommendation

Implement this redesign as an artifact-first migration, not a search-layer wrapper. The main failure today is not only retrieval scoring; it is that the system does not yet have stable narrative units or stable identity units. `scene_segments` and `character_registry` fix those two foundations first, which makes the later sparse/dense/hybrid/rerank split worthwhile instead of cosmetic.
