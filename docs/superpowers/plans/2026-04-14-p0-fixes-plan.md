# P0 问题修复实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复三个 P0 问题：检索层升级词级 TF-IDF、Planner 意图优先路由、验证层统一 confidence 字段。

**Architecture:** 分三个阶段按模块顺序实施，每个阶段独立可测试。阶段一升级检索层，阶段二重构 Planner 路由，阶段三简化验证层。

**Tech Stack:** Python 3.x, jieba 分词, scikit-learn TF-IDF, Pydantic, FastAPI

---

## 文件结构

| 文件 | 操作 | 职责 |
|------|------|------|
| `requirements.txt` | 修改 | 添加 jieba 依赖 |
| `novel_system/indexing.py` | 修改 | 词级 TF-IDF 构建 |
| `novel_system/search/orchestrator.py` | 修改 | TF-IDF 检索接入 |
| `novel_system/models.py` | 修改 | 新增 QueryIntent 枚举，更新 AskResponse/AskTrace |
| `novel_system/planner.py` | 修改 | 意图检测和路由逻辑 |
| `novel_system/service.py` | 修改 | confidence 逻辑，删除 uncertainty 错误代码 |
| `novel_system/tracing.py` | 修改 | AskTrace 使用 confidence |
| `tests/test_tfidf_retrieval.py` | 新建 | TF-IDF 检索测试 |
| `tests/test_planner_intent.py` | 新建 | Planner 意图检测测试 |
| `tests/test_validation_confidence.py` | 新建 | 验证层 confidence 测试 |

---

## 阶段一：检索层重构

### Task 1: 添加 jieba 依赖

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: 添加 jieba 依赖到 requirements.txt**

```python
fastapi>=0.135
uvicorn>=0.44
python-multipart>=0.0.26
numpy>=2.3
scikit-learn>=1.7
pydantic>=2.12
requests>=2.32
jinja2>=3.1
python-json-logger>=2.0.0
jieba>=0.42.1
```

- [ ] **Step 2: 安装依赖验证**

Run: `conda run -n chaishu pip install jieba>=0.42.1`
Expected: Successfully installed jieba

- [ ] **Step 3: 提交依赖更新**

```bash
git add requirements.txt
git commit -m "chore: add jieba dependency for word-level TF-IDF"
```

---

### Task 2: 编写 TF-IDF 检索测试

**Files:**
- Create: `tests/test_tfidf_retrieval.py`

- [ ] **Step 1: 创建测试文件并编写 TF-IDF 检索测试**

```python
"""Tests for TF-IDF retrieval in SearchOrchestrator."""
import pytest
from sklearn.feature_extraction.text import TfidfVectorizer
import numpy as np

from novel_system.search.orchestrator import SearchOrchestrator


class MockBookIndexWithTFIDF:
    """Mock book index with TF-IDF vectors for testing."""

    def __init__(self):
        self.corpora = {
            "chapter_chunks": [
                {
                    "id": "ch1-chunk0",
                    "chapter": 1,
                    "text": "韩立被村里人叫作二愣子，他性格沉稳，做事谨慎。",
                    "target": "chapter_chunks",
                },
                {
                    "id": "ch1-chunk1",
                    "chapter": 1,
                    "text": "墨大夫是七玄门的供奉，负责教导弟子修炼。",
                    "target": "chapter_chunks",
                },
                {
                    "id": "ch2-chunk0",
                    "chapter": 2,
                    "text": "韩立参加七玄门的内门弟子测试，是因为三叔的推举。",
                    "target": "chapter_chunks",
                },
            ],
        }
        # 构建词级 TF-IDF
        texts = [doc["text"] for doc in self.corpora["chapter_chunks"]]
        self.vectorizers = {
            "chapter_chunks": TfidfVectorizer(
                tokenizer=self._tokenize,
                lowercase=False,
                min_df=1,
            )
        }
        self.matrices = {
            "chapter_chunks": self.vectorizers["chapter_chunks"].fit_transform(texts)
        }

    def _tokenize(self, text: str) -> list[str]:
        """简单分词用于测试"""
        import jieba
        return list(jieba.cut(text))


def test_tfidf_search_returns_relevant_results():
    """TF-IDF 检索应返回相关文档。"""
    orchestrator = SearchOrchestrator()
    index = MockBookIndexWithTFIDF()

    # 查询包含"韩立参加测试"
    hits = orchestrator.retrieve(
        book_index=index,
        query="韩立为什么参加测试",
        targets=["chapter_chunks"],
        chapter_scope=[],
        top_k=3,
    )

    # 应返回结果
    assert len(hits) > 0
    # 最相关的应该是包含"韩立参加测试"的文档
    top_hit = hits[0]
    assert "韩立" in top_hit.document.get("text", "")
    assert top_hit.score > 0


def test_tfidf_fallback_to_sparse_when_no_vectorizer():
    """无 TF-IDF 时应回退到字符级匹配。"""
    orchestrator = SearchOrchestrator()

    # 无 vectorizer 的 index
    class NoVectorIndex:
        corpora = {
            "chapter_chunks": [
                {"id": "ch1", "chapter": 1, "text": "韩立参加测试", "target": "chapter_chunks"}
            ]
        }
        vectorizers = {}
        matrices = {}

    index = NoVectorIndex()
    hits = orchestrator.retrieve(
        book_index=index,
        query="韩立",
        targets=["chapter_chunks"],
        chapter_scope=[],
        top_k=3,
    )

    # 应通过字符匹配返回结果
    assert len(hits) > 0


def test_tfidf_search_respects_chapter_scope():
    """TF-IDF 检索应遵循章节范围限制。"""
    orchestrator = SearchOrchestrator()
    index = MockBookIndexWithTFIDF()

    # 限制在第 1 章
    hits = orchestrator.retrieve(
        book_index=index,
        query="韩立",
        targets=["chapter_chunks"],
        chapter_scope=[1],
        top_k=3,
    )

    # 所有结果应在第 1 章
    for hit in hits:
        assert hit.document.get("chapter") == 1


def test_tfidf_search_dedupe_results():
    """TF-IDF 检索应去重。"""
    orchestrator = SearchOrchestrator()
    index = MockBookIndexWithTFIDF()

    hits = orchestrator.retrieve(
        book_index=index,
        query="韩立",
        targets=["chapter_chunks"],
        chapter_scope=[],
        top_k=10,
    )

    # 检查去重
    doc_ids = [h.document.get("id") for h in hits]
    assert len(doc_ids) == len(set(doc_ids))
```

- [ ] **Step 2: 运行测试验证失败**

Run: `conda run -n chaishu python -m pytest tests/test_tfidf_retrieval.py -v`
Expected: FAIL (TF-IDF retrieval not implemented yet)

- [ ] **Step 3: 提交测试文件**

```bash
git add tests/test_tfidf_retrieval.py
git commit -m "test: add TF-IDF retrieval tests (expecting failure)"
```

---

### Task 3: 实现词级 TF-IDF 构建

**Files:**
- Modify: `novel_system/indexing.py`

- [ ] **Step 1: 在 indexing.py 顶部添加 jieba 导入**

在 `novel_system/indexing.py` 文件中，找到导入区域（约第 13 行后），添加：

```python
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
import jieba  # 新增

from .config import AppConfig
```

- [ ] **Step 2: 在 BookIndexer 类中添加分词方法**

找到 `BookIndexer` 类定义，在类中添加分词方法：

```python
def _tokenize_chinese(self, text: str) -> list[str]:
    """中文分词，用于 TF-IDF。"""
    return list(jieba.cut(text))
```

- [ ] **Step 3: 修改 _build_vector_payload 方法**

找到 `_build_vector_payload` 方法（约 588-601 行），替换为：

```python
def _build_vector_payload(self, docs: list[dict[str, Any]]) -> dict[str, Any]:
    """构建词级 TF-IDF 向量。"""
    texts = [doc["text"] for doc in docs]
    if not texts:
        return {"vectorizer": None, "matrix": None}

    # 词级 TF-IDF
    vectorizer = TfidfVectorizer(
        tokenizer=self._tokenize_chinese,
        lowercase=False,
        min_df=1,
        max_features=50000,
        dtype=np.float32,
    )
    matrix = vectorizer.fit_transform(texts)
    return {"vectorizer": vectorizer, "matrix": matrix}
```

- [ ] **Step 4: 运行现有测试验证无回归**

Run: `conda run -n chaishu python -m pytest tests/test_index_pipeline.py -v`
Expected: PASS

- [ ] **Step 5: 提交索引构建修改**

```bash
git add novel_system/indexing.py
git commit -m "feat: upgrade TF-IDF to word-level with jieba tokenizer"
```

---

### Task 4: 实现 TF-IDF 检索接入

**Files:**
- Modify: `novel_system/search/orchestrator.py`

- [ ] **Step 1: 在 SearchOrchestrator 类中添加 _tfidf_search 方法**

在 `novel_system/search/orchestrator.py` 文件中，找到 `_sparse_fallback` 方法之前，添加：

```python
def _tfidf_search(
    self,
    query: str,
    docs: list[dict[str, Any]],
    vectorizer: Any,
    matrix: Any,
    target: str,
    top_k: int,
) -> list[dict[str, Any]]:
    """使用 TF-IDF 进行检索。

    Args:
        query: 查询文本
        docs: 文档列表
        vectorizer: TF-IDF vectorizer
        matrix: TF-IDF 矩阵
        target: 检索目标名称
        top_k: 返回数量

    Returns:
        命中结果列表
    """
    if not docs or matrix is None:
        return []

    query_vec = vectorizer.transform([query])
    scores = (matrix @ query_vec.T).toarray().ravel()
    top_indices = scores.argsort()[-top_k:][::-1]

    hits = []
    for idx in top_indices:
        if scores[idx] > 0 and idx < len(docs):
            hits.append({
                "target": target,
                "document_id": docs[idx].get("id", f"doc-{idx}"),
                "document": docs[idx],
                "score": float(scores[idx]),
            })
    return hits
```

- [ ] **Step 2: 修改 retrieve 方法接入 TF-IDF**

找到 `retrieve` 方法（约 26-62 行），替换为：

```python
def retrieve(
    self,
    *,
    book_index: Any,
    query: str,
    targets: list[str],
    chapter_scope: list[int],
    top_k: int,
) -> list[Hit]:
    """Retrieve candidates from multiple targets.

    Args:
        book_index: Book index with corpora dict.
        query: User query string.
        targets: List of target names to search.
        chapter_scope: Chapter range for filtering.
        top_k: Maximum results to return.

    Returns:
        List of Hit objects sorted by score.
    """
    hits: list[dict[str, Any]] = []
    for target in targets:
        docs = list(book_index.corpora.get(target, []))
        # Filter by chapter scope
        if chapter_scope:
            docs = [doc for doc in docs if self._in_scope(doc, chapter_scope)]

        # 特殊处理：character_card 精确别名匹配
        if target == "character_card":
            alias_hits = self._exact_character_hits(query, docs)
            hits.extend(alias_hits)

        # TF-IDF 检索
        vectorizer = book_index.vectorizers.get(target)
        matrix = book_index.matrices.get(target)

        if vectorizer is not None and matrix is not None:
            tfidf_hits = self._tfidf_search(query, docs, vectorizer, matrix, target, top_k)
            hits.extend(tfidf_hits)
        else:
            # 回退到字符级匹配
            hits.extend(self._sparse_fallback(query, docs, target))

    deduped = self._dedupe_candidates(hits)
    deduped.sort(key=lambda item: item["score"], reverse=True)
    return [
        Hit(target=item["target"], document=item["document"], score=item["score"])
        for item in deduped[:top_k]
    ]
```

- [ ] **Step 3: 运行 TF-IDF 检索测试验证通过**

Run: `conda run -n chaishu python -m pytest tests/test_tfidf_retrieval.py -v`
Expected: PASS

- [ ] **Step 4: 运行现有测试验证无回归**

Run: `conda run -n chaishu python -m pytest tests/test_search_orchestrator.py -v`
Expected: PASS

- [ ] **Step 5: 提交 TF-IDF 检索实现**

```bash
git add novel_system/search/orchestrator.py
git commit -m "feat: integrate word-level TF-IDF retrieval into SearchOrchestrator"
```

---

### Task 5: 阶段一验收测试

- [ ] **Step 1: 运行所有相关测试**

Run: `conda run -n chaishu python -m pytest tests/test_tfidf_retrieval.py tests/test_search_orchestrator.py tests/test_index_pipeline.py -v`
Expected: All PASS

- [ ] **Step 2: 手动验证检索效果（可选）**

```bash
conda run -n chaishu python -c "
from novel_system.indexing import BookIndexer
from novel_system.search.orchestrator import SearchOrchestrator

# 测试分词效果
import jieba
text = '韩立为什么会去参加七玄门的内门弟子测试'
print('分词结果:', list(jieba.cut(text)))
"
```

- [ ] **Step 3: 标记阶段一完成**

```bash
git tag -a "phase1-tfidf-complete" -m "Phase 1: TF-IDF retrieval implemented"
```

---

## 阶段二：Planner 意图优先路由

### Task 6: 添加 QueryIntent 枚举

**Files:**
- Modify: `novel_system/models.py`

- [ ] **Step 1: 在 models.py 中添加 QueryIntent 枚举**

在 `novel_system/models.py` 文件中，在 `TaskType` 定义之前（约第 9 行前），添加：

```python
from enum import Enum, auto


class QueryIntent(Enum):
    """查询意图类型。"""
    CAUSAL_CHAIN = auto()       # 因果链：为什么、怎么、原因、结果
    FACT_QUERY = auto()         # 事实查询：是什么、有哪些
    CHARACTER_ANALYSIS = auto() # 人物分析：性格、外貌、是谁
    SUMMARY = auto()            # 总结：概括、摘要
    TEMPORAL = auto()           # 时间相关：什么时候、后来
    GENERAL = auto()            # 通用查询
```

- [ ] **Step 2: 运行验证导入正常**

Run: `conda run -n chaishu python -c "from novel_system.models import QueryIntent; print(QueryIntent.CAUSAL_CHAIN)"`
Expected: `QueryIntent.CAUSAL_CHAIN`

- [ ] **Step 3: 提交枚举定义**

```bash
git add novel_system/models.py
git commit -m "feat: add QueryIntent enum for intent-based routing"
```

---

### Task 7: 编写 Planner 意图检测测试

**Files:**
- Create: `tests/test_planner_intent.py`

- [ ] **Step 1: 创建测试文件并编写意图检测测试**

```python
"""Tests for Planner intent-based routing."""
import pytest
from novel_system.planner import RuleBasedPlanner
from novel_system.models import QueryIntent, Scope, ConversationTurn


@pytest.fixture
def planner():
    return RuleBasedPlanner()


class TestIntentDetection:
    """测试意图检测。"""

    def test_detect_causal_chain_intent(self, planner):
        """因果链查询应检测为 CAUSAL_CHAIN。"""
        assert planner._detect_intent("韩立为什么参加测试") == QueryIntent.CAUSAL_CHAIN
        assert planner._detect_intent("怎么修炼象甲功") == QueryIntent.CAUSAL_CHAIN
        assert planner._detect_intent("原因是什么") == QueryIntent.CAUSAL_CHAIN

    def test_detect_fact_query_intent(self, planner):
        """事实查询应检测为 FACT_QUERY。"""
        assert planner._detect_intent("象甲功是什么") == QueryIntent.FACT_QUERY
        assert planner._detect_intent("七玄门有哪些堂口") == QueryIntent.FACT_QUERY

    def test_detect_character_analysis_intent(self, planner):
        """人物分析查询应检测为 CHARACTER_ANALYSIS。"""
        assert planner._detect_intent("韩立是谁") == QueryIntent.CHARACTER_ANALYSIS
        assert planner._detect_intent("韩立的性格怎么样") == QueryIntent.CHARACTER_ANALYSIS
        assert planner._detect_intent("墨大夫的外貌") == QueryIntent.CHARACTER_ANALYSIS

    def test_detect_summary_intent(self, planner):
        """总结查询应检测为 SUMMARY。"""
        assert planner._detect_intent("总结第一章") == QueryIntent.SUMMARY
        assert planner._detect_intent("概括韩立的经历") == QueryIntent.SUMMARY

    def test_detect_temporal_intent(self, planner):
        """时间相关查询应检测为 TEMPORAL。"""
        assert planner._detect_intent("韩立后来怎么样了") == QueryIntent.TEMPORAL
        assert planner._detect_intent("结局是什么") == QueryIntent.TEMPORAL

    def test_detect_general_intent(self, planner):
        """未匹配的查询应检测为 GENERAL。"""
        assert planner._detect_intent("韩立") == QueryIntent.GENERAL
        assert planner._detect_intent("七玄门") == QueryIntent.GENERAL


class TestIntentBasedRouting:
    """测试意图优先路由。"""

    def test_causal_query_not_prioritize_character_card(self, planner):
        """因果链查询不应优先检索 character_card。"""
        output, _ = planner.plan(
            query="韩立为什么参加七玄门测试",
            scope=Scope(),
            history=[],
        )

        # event_timeline 应该在前面
        assert "event_timeline" in output.retrieval_targets
        # character_card 不应在第一位
        if "character_card" in output.retrieval_targets:
            assert output.retrieval_targets[0] != "character_card"

    def test_character_analysis_prioritize_character_card(self, planner):
        """人物分析查询应优先检索 character_card。"""
        output, _ = planner.plan(
            query="韩立是谁",
            scope=Scope(),
            history=[],
        )

        # character_card 应该在第一位
        assert output.retrieval_targets[0] == "character_card"

    def test_fact_query_targets_chapter_chunks(self, planner):
        """事实查询应检索 chapter_chunks。"""
        output, _ = planner.plan(
            query="象甲功是什么",
            scope=Scope(),
            history=[],
        )

        assert "chapter_chunks" in output.retrieval_targets

    def test_temporal_query_targets_event_timeline(self, planner):
        """时间相关查询应检索 event_timeline。"""
        output, _ = planner.plan(
            query="韩立后来怎么样了",
            scope=Scope(),
            history=[],
        )

        assert "event_timeline" in output.retrieval_targets


class TestRetrievalIntent:
    """测试 retrieval_intent 映射。"""

    def test_causal_chain_has_causal_chain_intent(self, planner):
        """因果链查询应有 causal_chain intent。"""
        output, _ = planner.plan(
            query="韩立为什么参加测试",
            scope=Scope(),
            history=[],
        )

        assert output.retrieval_intent == "causal_chain"

    def test_character_analysis_has_alias_resolution_intent(self, planner):
        """人物分析查询应有 alias_resolution intent。"""
        output, _ = planner.plan(
            query="韩立是谁",
            scope=Scope(),
            history=[],
        )

        assert output.retrieval_intent == "alias_resolution"
```

- [ ] **Step 2: 运行测试验证失败**

Run: `conda run -n chaishu python -m pytest tests/test_planner_intent.py -v`
Expected: FAIL (intent detection not implemented yet)

- [ ] **Step 3: 提交测试文件**

```bash
git add tests/test_planner_intent.py
git commit -m "test: add Planner intent detection tests (expecting failure)"
```

---

### Task 8: 实现意图检测方法

**Files:**
- Modify: `novel_system/planner.py`

- [ ] **Step 1: 在 planner.py 中导入 QueryIntent**

在 `novel_system/planner.py` 文件顶部，修改导入：

```python
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .models import ConversationTurn, PlannerOutput, Scope, QueryIntent
```

- [ ] **Step 2: 在 RuleBasedPlanner 类中添加意图配置**

在 `RuleBasedPlanner` 类定义中，`infer_memory` 方法之前，添加：

```python
class RuleBasedPlanner:
    """基于规则的查询规划器。"""

    # 意图关键词模式
    INTENT_PATTERNS: dict[QueryIntent, list[str]] = {
        QueryIntent.CAUSAL_CHAIN: ["为什么", "怎么", "原因", "结果", "怎么会", "怎么会这样"],
        QueryIntent.FACT_QUERY: ["是什么", "有哪些", "有没有", "是怎样的"],
        QueryIntent.CHARACTER_ANALYSIS: ["是谁", "性格", "外貌", "什么样的人", "人物卡"],
        QueryIntent.SUMMARY: ["总结", "概括", "摘要", "简介"],
        QueryIntent.TEMPORAL: ["什么时候", "后来", "之后", "之前", "最终", "结局"],
    }

    # 意图到检索目标的映射
    INTENT_TARGETS: dict[QueryIntent, list[str]] = {
        QueryIntent.CAUSAL_CHAIN: ["event_timeline", "chapter_chunks"],
        QueryIntent.FACT_QUERY: ["chapter_chunks", "canon_memory"],
        QueryIntent.CHARACTER_ANALYSIS: ["character_card", "chapter_chunks"],
        QueryIntent.SUMMARY: ["chapter_summaries", "event_timeline"],
        QueryIntent.TEMPORAL: ["event_timeline", "recent_plot"],
        QueryIntent.GENERAL: ["chapter_chunks"],
    }

    def infer_memory(self, history: list[ConversationTurn], scope: Scope) -> MemoryState:
        # ... 保持原有代码
```

- [ ] **Step 3: 添加意图检测方法**

在 `INTENT_TARGETS` 定义之后，`infer_memory` 方法之前，添加：

```python
def _detect_intent(self, query: str) -> QueryIntent:
    """检测查询意图（优先级最高）。

    Args:
        query: 用户查询

    Returns:
        检测到的意图类型
    """
    for intent, keywords in self.INTENT_PATTERNS.items():
        if any(kw in query for kw in keywords):
            return intent
    return QueryIntent.GENERAL

def _get_retrieval_intent(self, intent: QueryIntent) -> str:
    """根据意图返回检索意图。"""
    mapping = {
        QueryIntent.CAUSAL_CHAIN: "causal_chain",
        QueryIntent.CHARACTER_ANALYSIS: "alias_resolution",
    }
    return mapping.get(intent, "scene_evidence")

def _get_task_type(self, intent: QueryIntent, query: str) -> str:
    """根据意图返回任务类型。"""
    if intent == QueryIntent.SUMMARY:
        return "summary"
    if intent == QueryIntent.CHARACTER_ANALYSIS:
        return "analysis"
    return "qa"
```

- [ ] **Step 4: 运行意图检测测试**

Run: `conda run -n chaishu python -m pytest tests/test_planner_intent.py::TestIntentDetection -v`
Expected: PASS

- [ ] **Step 5: 提交意图检测实现**

```bash
git add novel_system/planner.py
git commit -m "feat: implement intent detection with QueryIntent enum"
```

---

### Task 9: 重构 plan 方法

**Files:**
- Modify: `novel_system/planner.py`

- [ ] **Step 1: 重构 plan 方法使用意图优先路由**

找到 `plan` 方法（约 156-257 行），替换为：

```python
def plan(
    self,
    query: str,
    scope: Scope,
    history: list[ConversationTurn],
    *,
    multimodal: bool = False,
) -> tuple[PlannerOutput, MemoryState]:
    """规划查询处理策略。

    Args:
        query: 用户查询
        scope: 章节范围
        history: 对话历史
        multimodal: 是否多模态

    Returns:
        (PlannerOutput, MemoryState) 元组
    """
    memory = self.infer_memory(history, scope)
    lowered = query.lower()

    # 版权请求处理
    if any(keyword in query for keyword in ("完整输出", "全文", "原文")):
        planner = PlannerOutput(
            task_type="copyright_request",
            retrieval_needed=False,
            retrieval_targets=[],
            retrieval_intent="copyright_guard",
            constraints=["copyright_guard"],
            success_criteria=["refuse_long_quote", "offer_summary"],
        )
        return planner, memory

    # 续写请求处理
    if any(keyword in query for keyword in ("续写", "继续写", "仿写")):
        planner = PlannerOutput(
            task_type="continuation",
            retrieval_needed=True,
            retrieval_targets=["recent_plot", "character_card", "canon_memory", "style_samples"],
            retrieval_intent="scene_evidence",
            constraints=["stay_in_scope", "no_direct_long_quote", "consistency_check_before_output"],
            success_criteria=["character_consistent", "no_spoiler_beyond_scope", "style_close"],
        )
        return planner, memory

    # 总结请求处理
    if any(keyword in query for keyword in ("总结", "摘要", "概括")):
        planner = PlannerOutput(
            task_type="summary",
            retrieval_needed=True,
            retrieval_targets=["chapter_summaries", "event_timeline", "chapter_chunks"],
            retrieval_intent="scene_evidence",
            constraints=["ordered_summary", "grounded_answer"],
            success_criteria=["key_events_covered", "no_spoiler_beyond_scope"],
        )
        return planner, memory

    # 抽取请求处理
    if any(keyword in query for keyword in ("人物卡", "时间线", "整理", "抽一张", "关系", "势力", "抽取")):
        retrieval_targets = ["character_card", "chapter_chunks"]
        if "时间线" in query:
            retrieval_targets = ["event_timeline", "chapter_chunks"]
        elif "关系" in query or "势力" in query:
            retrieval_targets = ["character_card", "relationship_graph", "world_rule", "chapter_summaries"]
        planner = PlannerOutput(
            task_type="extract",
            retrieval_needed=True,
            retrieval_targets=retrieval_targets,
            retrieval_intent="alias_resolution" if "人物" in query or "谁" in query else "scene_evidence",
            constraints=["structured_output", "grounded_answer"],
            success_criteria=["fields_complete", "no_spoiler_beyond_scope"],
        )
        return planner, memory

    # 分析请求处理
    if any(keyword in query for keyword in ("觉得", "性格", "分析", "怎么看")):
        planner = PlannerOutput(
            task_type="analysis",
            retrieval_needed=True,
            retrieval_targets=["character_card", "recent_plot"],
            retrieval_intent="alias_resolution",
            constraints=["brief_answer", "grounded_reason"],
            success_criteria=["clear_position", "evidence_backed"],
        )
        return planner, memory

    # === 意图优先路由（新增核心逻辑）===

    # 1. 检测意图（优先级最高）
    intent = self._detect_intent(query)

    # 2. 根据意图确定基础检索目标
    retrieval_targets = list(self.INTENT_TARGETS.get(intent, ["chapter_chunks"]))
    retrieval_intent = self._get_retrieval_intent(intent)

    # 3. 人名关键词作为辅助增强（不覆盖意图决策）
    person_keywords = ("韩立", "张铁", "墨大夫", "舞岩", "韩胖子", "三叔")
    if any(kw in query for kw in person_keywords) and intent != QueryIntent.CHARACTER_ANALYSIS:
        # 因果/事实问题：补充 character_card 用于上下文，但不优先
        if "character_card" not in retrieval_targets:
            retrieval_targets.append("character_card")

    # 4. 其他辅助逻辑
    if any(keyword in query for keyword in ("瓶子", "后来", "现在")):
        if "recent_plot" not in retrieval_targets:
            retrieval_targets.append("recent_plot")

    if multimodal:
        retrieval_targets = ["vision_parse", *retrieval_targets]

    planner = PlannerOutput(
        task_type=self._get_task_type(intent, query),
        retrieval_needed=True,
        retrieval_targets=list(dict.fromkeys(retrieval_targets)),
        retrieval_intent=retrieval_intent,
        constraints=["grounded_answer", "cite_evidence", "no_spoiler_beyond_scope"],
        success_criteria=["answer_correct", "answer_grounded"],
    )
    return planner, memory
```

- [ ] **Step 2: 删除旧的 FUTURE_RE 相关逻辑（已整合到意图检测）**

找到并删除以下代码（如果还存在）：

```python
# 删除这段（约 226-235 行）：
if FUTURE_RE.search(query):
    planner = PlannerOutput(
        task_type="qa",
        retrieval_needed=True,
        retrieval_targets=["recent_plot", "canon_memory", "chapter_chunks"],
        retrieval_intent="causal_chain",
        constraints=["grounded_answer", "cite_evidence", "no_spoiler_beyond_scope"],
        success_criteria=["answer_correct", "scope_guard"],
    )
    return planner, memory
```

以及删除旧的通用 QA 路由逻辑（约 237-257 行），因为已被新的意图优先路由替代。

- [ ] **Step 3: 运行所有 Planner 测试**

Run: `conda run -n chaishu python -m pytest tests/test_planner_intent.py -v`
Expected: PASS

- [ ] **Step 4: 提交 plan 方法重构**

```bash
git add novel_system/planner.py
git commit -m "feat: implement intent-first routing in plan method"
```

---

### Task 10: 阶段二验收测试

- [ ] **Step 1: 运行所有相关测试**

Run: `conda run -n chaishu python -m pytest tests/test_planner_intent.py -v`
Expected: All PASS

- [ ] **Step 2: 验证关键路由场景**

Run: `conda run -n chaishu python -c "
from novel_system.planner import RuleBasedPlanner
from novel_system.models import Scope

planner = RuleBasedPlanner()

# 测试因果链查询
output, _ = planner.plan('韩立为什么参加测试', Scope(), [])
print('因果链查询 targets:', output.retrieval_targets)
assert 'event_timeline' in output.retrieval_targets

# 测试人物分析查询
output, _ = planner.plan('韩立是谁', Scope(), [])
print('人物分析 targets:', output.retrieval_targets)
assert output.retrieval_targets[0] == 'character_card'

print('所有路由场景验证通过')
"`
Expected: All assertions pass

- [ ] **Step 3: 标记阶段二完成**

```bash
git tag -a "phase2-planner-complete" -m "Phase 2: Intent-first routing implemented"
```

---

## 阶段三：验证层简化

### Task 11: 编写 confidence 测试

**Files:**
- Create: `tests/test_validation_confidence.py`

- [ ] **Step 1: 创建测试文件**

```python
"""Tests for validation confidence field."""
import pytest
from novel_system.models import AskResponse, AskTrace
from novel_system.validator import AnswerValidator, EvidenceGateResult, EvidenceItem
from novel_system.models import Scope


class TestConfidenceField:
    """测试 confidence 字段。"""

    def test_ask_response_has_confidence_field(self):
        """AskResponse 应有 confidence 字段。"""
        response = AskResponse(
            planner=type('PlannerOutput', (), {'task_type': 'qa', 'retrieval_targets': [], 'retrieval_intent': 'scene_evidence', 'constraints': [], 'success_criteria': []})(),
            answer="测试答案",
            evidence=[],
            confidence="high",
            uncertainty="low",  # 向后兼容
            scope=Scope(),
        )
        assert response.confidence == "high"
        assert response.uncertainty == "low"

    def test_high_confidence_means_low_uncertainty(self):
        """高置信度应对应低不确定性。"""
        # 这个测试验证向后兼容逻辑
        response = AskResponse(
            planner=type('PlannerOutput', (), {'task_type': 'qa', 'retrieval_targets': [], 'retrieval_intent': 'scene_evidence', 'constraints': [], 'success_criteria': []})(),
            answer="测试答案",
            evidence=[],
            confidence="high",
            uncertainty="low",
            scope=Scope(),
        )
        # confidence=high 应该对应 uncertainty=low
        assert response.confidence == "high"
        assert response.uncertainty == "low"


class TestConfidenceUncertaintyMapping:
    """测试 confidence 和 uncertainty 的映射。"""

    def test_high_confidence_to_low_uncertainty(self):
        """high confidence 应映射到 low uncertainty。"""
        from novel_system.service import _compute_deprecated_uncertainty
        assert _compute_deprecated_uncertainty("high") == "low"

    def test_medium_confidence_to_medium_uncertainty(self):
        """medium confidence 应映射到 medium uncertainty。"""
        from novel_system.service import _compute_deprecated_uncertainty
        assert _compute_deprecated_uncertainty("medium") == "medium"

    def test_low_confidence_to_high_uncertainty(self):
        """low confidence 应映射到 high uncertainty。"""
        from novel_system.service import _compute_deprecated_uncertainty
        assert _compute_deprecated_uncertainty("low") == "high"
```

- [ ] **Step 2: 运行测试验证失败**

Run: `conda run -n chaishu python -m pytest tests/test_validation_confidence.py -v`
Expected: FAIL (confidence field and mapping function not implemented yet)

- [ ] **Step 3: 提交测试文件**

```bash
git add tests/test_validation_confidence.py
git commit -m "test: add confidence field tests (expecting failure)"
```

---

### Task 12: 更新 AskResponse 模型

**Files:**
- Modify: `novel_system/models.py`

- [ ] **Step 1: 修改 AskResponse 添加 confidence 字段**

找到 `AskResponse` 类（约 192-200 行），修改为：

```python
class AskResponse(BaseModel):
    planner: PlannerOutput
    answer: str
    evidence: list[EvidenceItem]
    confidence: Literal["low", "medium", "high"] = Field(
        default="medium",
        description="答案置信度：high=高置信度，low=低置信度"
    )
    uncertainty: Optional[Literal["low", "medium", "high"]] = Field(
        default=None,
        deprecated=True,
        description="已弃用，请使用 confidence 字段"
    )
    scope: Scope
    memory: dict[str, Any] = Field(default_factory=dict)
    warnings: list[APIWarning] = Field(default_factory=list)
    trace: Optional[AskTrace] = None
```

- [ ] **Step 2: 同样更新 ContinuationResponse**

找到 `ContinuationResponse` 类（约 203-210 行），修改为：

```python
class ContinuationResponse(BaseModel):
    planner: PlannerOutput
    answer: str
    evidence: list[EvidenceItem]
    confidence: Literal["low", "medium", "high"] = Field(
        default="medium",
        description="答案置信度"
    )
    uncertainty: Optional[Literal["low", "medium", "high"]] = Field(
        default=None,
        deprecated=True,
        description="已弃用，请使用 confidence 字段"
    )
    scope: Scope
    validation: dict[str, Any] = Field(default_factory=dict)
    trace: Optional[ContinuationTrace] = None
```

- [ ] **Step 3: 验证模型更新**

Run: `conda run -n chaishu python -c "from novel_system.models import AskResponse; print(AskResponse.model_fields.keys())"`
Expected: 包含 `confidence` 和 `uncertainty`

- [ ] **Step 4: 提交模型更新**

```bash
git add novel_system/models.py
git commit -m "feat: add confidence field to AskResponse, deprecate uncertainty"
```

---

### Task 13: 更新 AskTrace 模型

**Files:**
- Modify: `novel_system/models.py`

- [ ] **Step 1: 修改 AskTrace 使用 confidence**

找到 `AskTrace` 类（约 115-128 行），修改为：

```python
class AskTrace(BaseModel):
    """ask() 完整追踪"""
    trace_id: str
    book_id: str
    session_id: str
    timestamp: datetime
    query_rewrite: Optional[QueryRewriteTrace] = None
    planner: PlannerOutput
    retrieval: RetrievalTrace
    evidence_count: int
    evidence_spans: list[EvidenceSpan] = Field(default_factory=list)
    confidence: Literal["low", "medium", "high"]  # 替代 uncertainty
    total_duration_ms: float
    memory_state: dict[str, Any] = Field(default_factory=dict)
```

- [ ] **Step 2: 同样更新 ContinuationTrace**

找到 `ContinuationTrace` 类（约 131-145 行），修改为：

```python
class ContinuationTrace(BaseModel):
    """continue_story() 完整追踪"""
    trace_id: str
    book_id: str
    session_id: str
    timestamp: datetime
    query_rewrite: Optional[QueryRewriteTrace] = None
    planner: PlannerOutput
    retrieval: RetrievalTrace
    evidence_count: int
    evidence_spans: list[EvidenceSpan] = Field(default_factory=list)
    confidence: Literal["low", "medium", "high"]  # 替代 uncertainty
    validation: ValidationResult
    total_duration_ms: float
    memory_state: dict[str, Any] = Field(default_factory=dict)
```

- [ ] **Step 3: 提交 Trace 模型更新**

```bash
git add novel_system/models.py
git commit -m "feat: update AskTrace and ContinuationTrace to use confidence"
```

---

### Task 14: 更新 tracing.py 日志

**Files:**
- Modify: `novel_system/tracing.py`

- [ ] **Step 1: 修改 log_ask_trace 方法使用 confidence**

找到 `log_ask_trace` 方法（约 93-122 行），修改 `log_data` 中的字段：

```python
def log_ask_trace(self, trace: AskTrace) -> None:
    """记录 ask 追踪日志"""
    if not self._enabled:
        return

    log_data = {
        "trace_type": "ask",
        "trace_id": trace.trace_id,
        "book_id": trace.book_id,
        "session_id": trace.session_id,
        "timestamp": trace.timestamp.isoformat(),
        "query_original": trace.query_rewrite.original if trace.query_rewrite else None,
        "query_rewritten": trace.query_rewrite.rewritten if trace.query_rewrite else None,
        "query_expansions": trace.query_rewrite.expansions if trace.query_rewrite else [],
        "rewrite_duration_ms": trace.query_rewrite.duration_ms if trace.query_rewrite else None,
        "planner_task_type": trace.planner.task_type,
        "planner_retrieval_targets": trace.planner.retrieval_targets,
        "planner_constraints": trace.planner.constraints,
        "retrieval_targets": trace.retrieval.targets,
        "retrieval_hits_count": trace.retrieval.hits_count,
        "retrieval_duration_ms": trace.retrieval.duration_ms,
        "evidence_count": trace.evidence_count,
        "confidence": trace.confidence,  # 改为 confidence
        "total_duration_ms": round(trace.total_duration_ms, 2),
    }

    if HAS_JSON_LOGGER:
        self._logger.info("ask_trace", extra=log_data)
    else:
        self._logger.info(f"ask_trace: {json.dumps(log_data, ensure_ascii=False)}")
```

- [ ] **Step 2: 同样修改 log_continuation_trace 方法**

找到 `log_continuation_trace` 方法（约 124-155 行），修改 `log_data`：

```python
def log_continuation_trace(self, trace: ContinuationTrace) -> None:
    """记录续写追踪日志"""
    if not self._enabled:
        return

    log_data = {
        "trace_type": "continuation",
        "trace_id": trace.trace_id,
        "book_id": trace.book_id,
        "session_id": trace.session_id,
        "timestamp": trace.timestamp.isoformat(),
        "query_original": trace.query_rewrite.original if trace.query_rewrite else None,
        "query_rewritten": trace.query_rewrite.rewritten if trace.query_rewrite else None,
        "query_expansions": trace.query_rewrite.expansions if trace.query_rewrite else [],
        "rewrite_duration_ms": trace.query_rewrite.duration_ms if trace.query_rewrite else None,
        "planner_task_type": trace.planner.task_type,
        "planner_retrieval_targets": trace.planner.retrieval_targets,
        "planner_constraints": trace.planner.constraints,
        "retrieval_targets": trace.retrieval.targets,
        "retrieval_hits_count": trace.retrieval.hits_count,
        "retrieval_duration_ms": trace.retrieval.duration_ms,
        "evidence_count": trace.evidence_count,
        "confidence": trace.confidence,  # 改为 confidence
        "validation_adjusted": trace.validation.adjusted,
        "validation_notes": trace.validation.notes,
        "total_duration_ms": round(trace.total_duration_ms, 2),
    }

    if HAS_JSON_LOGGER:
        self._logger.info("continuation_trace", extra=log_data)
    else:
        self._logger.info(f"continuation_trace: {json.dumps(log_data, ensure_ascii=False)}")
```

- [ ] **Step 3: 提交 tracing 更新**

```bash
git add novel_system/tracing.py
git commit -m "feat: update trace logging to use confidence field"
```

---

### Task 15: 修复 service.py 验证逻辑

**Files:**
- Modify: `novel_system/service.py`

- [ ] **Step 1: 添加向后兼容转换函数**

在 `novel_system/service.py` 文件中，在导入区域后添加函数：

```python
def _compute_deprecated_uncertainty(confidence: str) -> str:
    """向后兼容：将 confidence 转换为旧 uncertainty 格式。

    Args:
        confidence: 置信度 ("low", "medium", "high")

    Returns:
        不确定性 (confidence 的反向)
    """
    mapping = {"high": "low", "medium": "medium", "low": "high"}
    return mapping.get(confidence, "medium")
```

- [ ] **Step 2: 修复 ask 方法中的置信度逻辑**

找到 `ask` 方法中处理验证结果的代码（约 728-731 行），替换为：

```python
# === 验证层: Answer Validator ===
validation_result = self.answer_validator.validate(
    query=request.user_query,
    answer=answer,
    evidence=evidence,
    gate_result=gate_result,
)

# 使用 validation_result 的置信度
confidence = validation_result.confidence

# SpoilerGuard 检测后调整置信度
if spoiler_risk.level == "high":
    confidence = "low"
elif spoiler_risk.level == "medium":
    # 降低一级
    if confidence == "high":
        confidence = "medium"
    elif confidence == "medium":
        confidence = "low"
```

- [ ] **Step 3: 更新 AskTrace 构建**

找到 `AskTrace` 构建代码（约 766-779 行），修改为：

```python
ask_trace = AskTrace(
    trace_id=trace_id,
    book_id=book_id,
    session_id=request.session_id,
    timestamp=datetime.now(),
    query_rewrite=query_rewrite_trace,
    planner=planner,
    retrieval=retrieval_trace,
    evidence_count=len(evidence),
    evidence_spans=evidence_spans,
    confidence=confidence,  # 使用 confidence
    total_duration_ms=round(total_duration, 2),
    memory_state=memory.to_dict(),
)
```

- [ ] **Step 4: 更新 AskResponse 构建**

找到 `return AskResponse` 代码（约 785-794 行），修改为：

```python
return AskResponse(
    planner=planner,
    answer=answer,
    evidence=evidence,
    confidence=confidence,
    uncertainty=_compute_deprecated_uncertainty(confidence),
    scope=request.scope,
    memory=memory.to_dict(),
    warnings=warnings,
    trace=ask_trace if request.debug else None,
)
```

- [ ] **Step 5: 提交 service.py 修复**

```bash
git add novel_system/service.py
git commit -m "fix: correct confidence logic and add backward compatibility"
```

---

### Task 16: 阶段三验收测试

- [ ] **Step 1: 运行所有相关测试**

Run: `conda run -n chaishu python -m pytest tests/test_validation_confidence.py -v`
Expected: All PASS

- [ ] **Step 2: 运行全量测试**

Run: `conda run -n chaishu python -m pytest tests/ -v`
Expected: All PASS

- [ ] **Step 3: 验证 confidence 和 uncertainty 关系正确**

Run: `conda run -n chaishu python -c "
from novel_system.service import _compute_deprecated_uncertainty

# 验证映射
assert _compute_deprecated_uncertainty('high') == 'low', 'high->low failed'
assert _compute_deprecated_uncertainty('medium') == 'medium', 'medium->medium failed'
assert _compute_deprecated_uncertainty('low') == 'high', 'low->high failed'

print('confidence->uncertainty 映射验证通过')
"`
Expected: All assertions pass

- [ ] **Step 4: 标记阶段三完成**

```bash
git tag -a "phase3-validation-complete" -m "Phase 3: Validation confidence simplified"
```

---

## 最终验收

### Task 17: 完整验收测试

- [ ] **Step 1: 运行所有测试**

Run: `conda run -n chaishu python -m pytest tests/ -v`
Expected: All PASS

- [ ] **Step 2: 验证检索效果提升**

Run: `conda run -n chaishu python -c "
from novel_system.planner import RuleBasedPlanner
from novel_system.models import Scope

planner = RuleBasedPlanner()

# 测试 1: 因果链查询
output, _ = planner.plan('韩立为什么参加七玄门测试', Scope(), [])
print('因果链查询 targets:', output.retrieval_targets)
assert 'event_timeline' in output.retrieval_targets, 'event_timeline missing'

# 测试 2: 人物分析查询
output, _ = planner.plan('韩立是谁', Scope(), [])
print('人物分析 targets:', output.retrieval_targets)
assert output.retrieval_targets[0] == 'character_card', 'character_card not first'

# 测试 3: confidence 验证
from novel_system.service import _compute_deprecated_uncertainty
assert _compute_deprecated_uncertainty('high') == 'low', 'mapping error'

print('\\n所有验收测试通过!')
"`
Expected: All assertions pass

- [ ] **Step 3: 创建最终提交**

```bash
git add -A
git commit -m "feat: complete P0 fixes - TF-IDF retrieval, intent routing, confidence field"
git tag -a "v1.1.0-p0-fixes" -m "P0 fixes complete: retrieval, planner, validation"
```

---

## 回滚计划

如果任何阶段出现问题，可通过以下方式回滚：

```bash
# 回滚到阶段一开始前
git checkout phase1-tfidf-complete~1

# 回滚到阶段二开始前
git checkout phase2-planner-complete~1

# 回滚到阶段三开始前
git checkout phase3-validation-complete~1
```
