# PRD: Vector Search Integration — Review Fixes & Completion

## Introduction

The `ralph/vector-search-integration` branch adds FAISS vector search, a CUDA embedding provider, a graph service, a reranker module, and query expansion to the novel Q&A system. A code review identified 2 critical bugs, several high-priority gaps, and medium/low issues. This PRD covers fixing all identified issues, wiring up the reranker, and getting the branch merge-ready.

## Goals

- Fix 2 critical bugs (broken import in `graph_service.py`, duplicated vector build in `service.py`)
- Wire `RuleBasedReranker` into the retrieval pipeline (`SearchOrchestrator` / `HybridRetriever`)
- Extract hardcoded character names from orchestrator into config
- Add missing test coverage: reranker, `_normalize_book_id`, `_extract_key_terms`, graph service
- Address all medium/low review issues
- All existing + new tests pass

## User Stories

### US-001: Commit uncommitted fixes for critical bugs
**Description:** As a developer, I need the working-tree fixes for `graph_service.py` imports and `service.py` duplication committed so the branch doesn't ship broken code.

**Acceptance Criteria:**
- [ ] `graph_service.py` uses explicit imports (not `from .service_shared import *`)
- [ ] `service.py:_run_book_index` delegates vector index building to `self.repo._build_vector_indexes()` instead of duplicating the logic
- [ ] `python -m novel_system.graph_service` imports without error
- [ ] `python -m pytest tests/ -x` passes

### US-002: Move jieba imports to module level in orchestrator
**Description:** As a developer, I need `jieba` and `jieba.posseg` imports moved out of `_extract_key_terms` to module level so they aren't re-imported on every retrieval call.

**Acceptance Criteria:**
- [ ] `import jieba` and `import jieba.posseg as pseg` appear at the top of `novel_system/search/orchestrator.py`
- [ ] `_extract_key_terms` no longer contains `import jieba` or `import jieba.posseg`
- [ ] Retrieval tests still pass: `python -m pytest tests/test_vector_retrieval.py tests/test_tfidf_retrieval.py -x`

### US-003: Extract hardcoded character names to config
**Description:** As a developer, I need the hardcoded character name list `["韩立", "张铁", "墨大夫", "三叔"]` in `orchestrator._extract_key_terms` moved to `AppConfig` or a constants file so it can be overridden per-book.

**Acceptance Criteria:**
- [ ] Add `common_character_names: list[str]` field to `AppConfig` with the current 4 names as default
- [ ] `_extract_key_terms` reads from config instead of a hardcoded list
- [ ] `SearchOrchestrator.retrieve()` accepts an optional config or name list parameter
- [ ] Existing retrieval tests pass without changes (defaults match current behavior)

### US-004: Wire reranker into retrieval pipeline
**Description:** As a user, I want the `RuleBasedReranker` to be active during retrieval so that search results are reranked for better relevance.

**Acceptance Criteria:**
- [ ] `HybridRetriever.__init__` accepts an optional `reranker: BaseReranker | None` parameter
- [ ] `HybridRetriever.retrieve()` applies reranking after orchestrator returns hits, before returning to caller
- [ ] `NovelSystemService` creates a `RuleBasedReranker` instance and passes it to `HybridRetriever`
- [ ] Reranker can be disabled via config (`reranker_type: "none"`)
- [ ] Chapter scope is passed to `reranker.rerank()` when available
- [ ] `python -m pytest tests/ -x` passes

### US-005: Add reranker unit tests
**Description:** As a developer, I need tests for `RuleBasedReranker` to verify reranking logic and edge cases.

**Acceptance Criteria:**
- [ ] New file `tests/test_reranker.py`
- [ ] Test: rerank with empty candidates returns empty list
- [ ] Test: rerank with mock `RetrievalHit` objects returns sorted by `final_score`
- [ ] Test: entity match scoring — query entities present in doc boost score
- [ ] Test: chapter relevance — doc near scope center scores higher than edge
- [ ] Test: target type weights — `character_card` scores higher than `recent_plot` for same content
- [ ] Test: `is_ready` property returns `True`
- [ ] `python -m pytest tests/test_reranker.py -x` passes

### US-006: Add `_normalize_book_id` unit tests
**Description:** As a developer, I need unit tests for the `_normalize_book_id` function in `api.py`.

**Acceptance Criteria:**
- [ ] New test file or new tests in `tests/test_book_import_artifacts.py`
- [ ] Test: single-encoded ID returns unchanged
- [ ] Test: double-encoded ID decodes correctly
- [ ] Test: triple-encoded ID decodes correctly (up to 3 iterations)
- [ ] Test: non-ASCII ID (e.g. Chinese characters) passes through unchanged
- [ ] Test: plain ASCII ID returns unchanged
- [ ] `python -m pytest tests/ -x` passes

### US-007: Add `_extract_key_terms` unit tests
**Description:** As a developer, I need tests for the key term extraction logic in `SearchOrchestrator`.

**Acceptance Criteria:**
- [ ] New file `tests/test_key_terms.py` or tests in `tests/test_tfidf_retrieval.py`
- [ ] Test: extracts nouns and proper nouns from Chinese query
- [ ] Test: extracts quoted terms as exact matches
- [ ] Test: filters stopwords ("什么", "怎么", etc.)
- [ ] Test: returns empty list for pure stopword query
- [ ] `python -m pytest tests/ -x` passes

### US-008: Fix FAISS delete behavior documentation
**Description:** As a developer, I need the `FAISSVectorStore.delete()` limitation documented and `compact()` made more robust.

**Acceptance Criteria:**
- [ ] `delete()` docstring clearly states it's a logical delete and vectors remain in FAISS index
- [ ] `compact()` docstring states it relies on FAISS internal `xb` attribute
- [ ] `compact()` handles the case where `xb` is not available (e.g. GPU index) with a warning log
- [ ] `count()` docstring clarifies it returns logical count (excluding deleted)

### US-009: Fix reranker neutral score for missing chapter data
**Description:** As a developer, I need `_compute_chapter_relevance` to return 0.0 (not 0.5) when no scope is provided or chapter is missing, so missing data doesn't inflate scores.

**Acceptance Criteria:**
- [ ] `_compute_chapter_relevance` returns 0.0 when `scope` is `None` or empty
- [ ] `_compute_chapter_relevance` returns 0.0 when document has no chapter info and no active_range
- [ ] Reranker tests updated to reflect new neutral score
- [ ] `python -m pytest tests/test_reranker.py -x` passes

### US-010: Add logging to `list_books` retry loop
**Description:** As a developer, I need the `list_books` retry loop in `indexing.py` to log warnings on `JSONDecodeError` so operators know a manifest is corrupt.

**Acceptance Criteria:**
- [ ] Each retry attempt logs a warning with the manifest path and error message
- [ ] Final failure (after 3 attempts) raises with the original error
- [ ] `python -m pytest tests/test_index_pipeline.py -x` passes

### US-011: Add FAISS search filter over-fetch documentation
**Description:** As a developer, I need the `FAISSVectorStore.search()` filter limitation documented so callers know to over-fetch.

**Acceptance Criteria:**
- [ ] `search()` docstring documents that `filter` is applied post-search and may reduce result count below `top_k`
- [ ] Docstring recommends callers pass `top_k * N` when using filters that may exclude many results
- [ ] No behavior change — this is documentation only

### US-012: Final verification
**Description:** As a developer, I need to verify the entire test suite passes and the branch is merge-ready.

**Acceptance Criteria:**
- [ ] `python -m pytest tests/ -x` passes with 0 failures
- [ ] `git status` shows no uncommitted changes (all fixes committed)
- [ ] No `from .service_shared import *` anywhere in the codebase
- [ ] No duplicated vector index building logic between `indexing.py` and `service.py`

## Functional Requirements

- FR-1: `graph_service.py` must import from explicit modules, not star-import from a nonexistent file
- FR-2: Vector index building must be delegated to a single method in `BookIndexRepository`, not duplicated
- FR-3: `jieba` imports in `orchestrator.py` must be at module level
- FR-4: Common character names must be configurable via `AppConfig`, not hardcoded in orchestrator
- FR-5: `RuleBasedReranker` must be wired into `HybridRetriever` and active during retrieval
- FR-6: Reranker must be disableable via config
- FR-7: `FAISSVectorStore.delete()` must be documented as logical-only
- FR-8: `_compute_chapter_relevance` must return 0.0 for missing data, not 0.5
- FR-9: `list_books` retry must log warnings on corrupt manifests
- FR-10: New tests must cover reranker, normalize_book_id, key_terms extraction

## Non-Goals

- No GPU-accelerated FAISS index (IVF, HNSW) — keep IndexFlat for simplicity
- No cross-book vector search
- No streaming/async embedding computation
- No UI changes for the graph service (backend only)
- No performance benchmarking or optimization beyond the import fix

## Technical Considerations

- The reranker's `rerank()` signature accepts `candidates: list[Any]` — it handles both `RetrievalHit` objects and dicts. When wiring into `HybridRetriever`, pass the `RetrievalHit` list directly.
- Chapter scope is a `list[int]` (typically `[start, end]`). The reranker expects the same format.
- `AppConfig` is a dataclass — adding `common_character_names` requires a default value to avoid breaking existing configs.
- The `FAISSVectorStore.compact()` method accesses `self._index.xb` which is only available on `IndexFlat*` types. If the index type changes in the future, compact will silently do nothing.

## Success Metrics

- All 2 critical bugs resolved (no broken imports, no duplicated logic)
- Reranker is active in the retrieval pipeline and improves result ordering
- Test count increases from 26 to 40+ (reranker, normalize, key_terms, graph)
- Zero test failures across the full suite
- No hardcoded domain-specific constants in generic retrieval code

## Open Questions

- Should the reranker's weight blend (`original_score * 0.4 + rerank_score * 0.6`) be configurable via `AppConfig`, or is the fixed ratio acceptable for now?
- Should `_extract_key_terms` support English terms (for mixed-language novels), or is Chinese-only sufficient?
- Should the graph service have integration tests, or are the existing unit tests in other modules sufficient coverage for now?
