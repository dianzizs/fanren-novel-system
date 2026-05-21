# 2026-05-22 Knowledge Graph Filtering Design

## Introduction
The Knowledge Graph in the Fanren Novel System currently suffers from noise issues. Many non-character entities (e.g., "时间", "方法", "成功", "章完", "许多") are incorrectly identified as characters and displayed as nodes, rendering the graph visually cluttered and semantically meaningless. In addition, character name suffixes like "现" (e.g., "韩立现") are not correctly normalized to their canonical form (e.g., "韩立").

This document proposes a dual-layered fix:
1. **LLM-Based Candidate Filtering**: An LLM-based filtering step using the MiniMax API in the indexing pipeline to cleanse extracted candidate names before they are written to indexing artifacts (specifically `character_card` and `character_registry`).
2. **Algorithmic Normalization Fixes**: Fix bugs in `graph_name_policy.py` where self-matching in the candidate normalization loops bypassed naming validation checks and prevented correct suffix/prefix merging.

---

## Component Details

### 1. `novel_system/indexing.py`
Add `_filter_names_with_llm` to the `BookIndexRepository` class.
- **Trigger**: Run prior to `_build_character_cards` and `_build_character_registry` during the indexing process (`build_from_txt`).
- **Logic**:
  - Divide raw name candidates into chunks of 50.
  - Send chunks to MiniMax API with a few-shot prompt asking to classify names as valid novel characters vs generic noise.
  - Only retain validated names for generating `character_card.json` and `character_registry.json`.

### 2. `novel_system/graph_name_policy.py`
Fix three bugs in `normalize_name_with_profile` and `filter_candidates_with_evidence`:
- **Bug 1**: Self-matching (`name == base`) in the normalization loop was returning the candidate directly, bypassing the `looks_like_graph_name` check and causing generic words (like "时间") to be returned as valid.
- **Bug 2**: Self-matching prevented matching of shorter, valid canonical prefixes/suffixes (e.g. "韩立现" matched "韩立现" first instead of "韩立").
- **Bug 3**: `filter_candidates_with_evidence` populated `known_names` with raw candidates without filtering them with `looks_like_graph_name`.

---

## Verification Plan

### Automated Tests
- Run existing unit tests via `conda run -n chaishu python -m pytest` to ensure no regressions.
- Add unit tests for `normalize_name_with_profile` covering suffix matching (e.g. "韩立现" -> "韩立") and rejection of generic words (e.g. "时间" -> `None`).

### Manual Verification
- Run indexing on the book `凡人修仙传` or `凡人修仙传-1-500章-txt`:
  ```bash
  conda run -n chaishu python scripts/reindex.py --book-id 凡人修仙传
  ```
- Inspect the generated `character_registry.json` and `character_card.json` to confirm they no longer contain generic words ("时间", "成功", "方法").
- Query the interactive graph endpoint and confirm the graph no longer displays noisy green nodes.
