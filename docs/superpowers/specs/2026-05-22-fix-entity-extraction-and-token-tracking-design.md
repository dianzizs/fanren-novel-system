# Entity Extraction and Token Tracking Fix Design

## 1. Problem Context

This document outlines the fixes for two independent issues observed in the novel processing system:
1.  **Invalid Knowledge Graph Nodes**: The system erroneously extracts entities containing trailing action verbs (e.g., "韩立撞").
2.  **Zero Token Consumption**: The UI reports 0 tokens consumed for indexing operations, despite LLM usage during the indexing phase.

## 2. Solutions

### 2.1. Fixing Entity Extraction (Invalid Nodes)

**Approach**: Expand the heuristic blocklist and strengthen the LLM filtering prompt.

**Implementation Details**:
*   **Expand `BAD_NAME_ENDINGS`**:
    *   Files: `novel_system/indexing.py` and `novel_system/artifacts/scene_segments.py`.
    *   Action: Add common Chinese action verbs (e.g., "撞", "退", "杀", "打", "飞", "跃", "走", "跑", "笑", "怒", "死", "伤", "闪", "躲", "躲") to the existing `BAD_NAME_ENDINGS` string/set.
*   **Strengthen LLM Prompt**:
    *   File: `novel_system/indexing.py` in `_filter_names_with_llm`.
    *   Action: Update the system prompt to explicitly instruct the model to reject noun phrases containing trailing verbs. Add negative examples like "韩立撞" -> "无" to guide the LLM's classification logic.

### 2.2. Fixing Token Tracking

**Approach**: Inject a callback function to bubble up token usage from the lower-level repository layer to the service layer.

**Implementation Details**:
*   **Inject Callback in Repository**:
    *   File: `novel_system/indexing.py` (`BookIndexRepository` class).
    *   Action: Update `build_from_txt` to accept an optional `token_callback: Callable[[dict[str, int]], None] | None = None`. Cascade this parameter down to the internal methods that eventually call `_filter_names_with_llm`.
*   **Invoke Callback**:
    *   File: `novel_system/indexing.py` in `_filter_names_with_llm`.
    *   Action: After receiving the `LLMResponse`, check if `token_callback` is provided and if the response contains `usage` data. If so, invoke `token_callback(response.usage)`.
*   **Provide Callback from Service**:
    *   File: `novel_system/services/indexing.py` (Assuming `IndexingServiceMixin` triggers `build_from_txt`).
    *   Action: When invoking `repo.build_from_txt(book_id, ...)`, pass a callback that wraps `self._record_token_usage(book_id, usage)` (which already exists in `StatsServiceMixin`).

## 3. Scope and Impact

*   **Scope**: The changes are strictly localized to `indexing.py`, `scene_segments.py`, and the service file responsible for triggering the build (likely `services/indexing.py`).
*   **Impact**:
    *   Entity extraction will become slightly more accurate, producing cleaner knowledge graphs without noticeably affecting performance.
    *   The Token Tracking UI will accurately reflect the LLMs cost incurred during the indexing phase.

## 4. Unresolved Ambiguities
*   None. The solution paths are deterministic and rely on existing system architectures.
