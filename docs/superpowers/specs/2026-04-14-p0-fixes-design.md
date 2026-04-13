# P0 问题修复设计方案

**日期**: 2026-04-14
**状态**: 待实现
**关联审计报告**: AUDIT_REPORT.md

---

## 概述

本文档针对 AUDIT_REPORT.md 中识别的三个 P0 问题，按模块顺序提供修复方案：

1. **检索层重构** - SearchOrchestrator 接入词级 TF-IDF
2. **Planner 意图优先路由** - 根据查询意图决定检索目标
3. **验证层简化** - 移除 uncertainty 字段，统一使用 confidence

---

## 设计一：检索层重构

### 目标

将 SearchOrchestrator 从"字符计数"升级为"词级 TF-IDF 检索"，提升召回率和准确率。

### 改动文件

| 文件 | 改动类型 | 说明 |
|------|---------|------|
| requirements.txt | 新增依赖 | 添加 jieba 分词库 |
| novel_system/indexing.py | 修改 | TF-IDF 构建逻辑升级为词级 |
| novel_system/search/orchestrator.py | 修改 | 接入 TF-IDF 检索 |

### 详细设计

#### 1. 引入 jieba 分词依赖

```python
# requirements.txt 添加
jieba>=0.42.1
```

#### 2. 修改 indexing.py 的 TF-IDF 构建

新增分词方法：

```python
import jieba

def _tokenize_chinese(self, text: str) -> list[str]:
    """中文分词"""
    return list(jieba.cut(text))
```

修改 `_build_vector_payload` 方法：

```python
def _build_vector_payload(self, docs: list[dict[str, Any]]) -> dict[str, Any]:
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

#### 3. 修改 SearchOrchestrator.retrieve()

新增 `_tfidf_search` 方法：

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
    """使用 TF-IDF 进行检索"""
    query_vec = vectorizer.transform([query])
    scores = (matrix @ query_vec.T).toarray().ravel()
    top_indices = scores.argsort()[-top_k:][::-1]

    hits = []
    for idx in top_indices:
        if scores[idx] > 0 and idx < len(docs):
            hits.append({
                "target": target,
                "document_id": docs[idx].get("id"),
                "document": docs[idx],
                "score": float(scores[idx]),
            })
    return hits
```

修改 `retrieve` 方法：

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
    hits: list[dict[str, Any]] = []

    for target in targets:
        docs = list(book_index.corpora.get(target, []))
        if chapter_scope:
            docs = [doc for doc in docs if self._in_scope(doc, chapter_scope)]

        # 特殊处理：character_card 精确别名匹配
        if target == "character_card":
            alias_hits = self._exact_character_hits(query, docs)
            hits.extend(alias_hits)

        # TF-IDF 检索
        vectorizer = book_index.vectorizers.get(target)
        matrix = book_index.matrices.get(target)

        if vectorizer and matrix:
            tfidf_hits = self._tfidf_search(query, docs, vectorizer, matrix, target, top_k)
            hits.extend(tfidf_hits)
        else:
            # 回退到字符级匹配
            hits.extend(self._sparse_fallback(query, docs, target))

    return self._dedupe_and_sort(hits, top_k)

def _dedupe_and_sort(self, hits: list[dict[str, Any]], top_k: int) -> list[Hit]:
    """去重并排序"""
    deduped = self._dedupe_candidates(hits)
    deduped.sort(key=lambda item: item["score"], reverse=True)
    return [
        Hit(target=item["target"], document=item["document"], score=item["score"])
        for item in deduped[:top_k]
    ]
```

#### 4. 索引重建

修改后需要重建所有书籍的索引：

```bash
conda run -n chaishu python scripts/build_index.py --rebuild-all
```

### 验收标准

- 运行 `qa_001` 测试用例，检索命中文档包含正确答案
- TF-IDF 分数排序合理（高相关文档排在前面）
- 无 TF-IDF 数据时正确回退到字符级匹配

---

## 设计二：Planner 意图优先路由

### 目标

将 Planner 从"关键词匹配"升级为"意图优先路由"，根据查询意图决定检索目标，解决 character_card 过度优先的问题。

### 改动文件

| 文件 | 改动类型 | 说明 |
|------|---------|------|
| novel_system/planner.py | 修改 | 新增意图检测和路由逻辑 |
| novel_system/models.py | 修改 | 新增 QueryIntent 枚举 |

### 详细设计

#### 1. 新增查询意图枚举

在 `models.py` 中添加：

```python
from enum import Enum, auto

class QueryIntent(Enum):
    """查询意图类型"""
    CAUSAL_CHAIN = auto()       # 因果链：为什么、怎么、原因、结果
    FACT_QUERY = auto()         # 事实查询：是什么、有哪些
    CHARACTER_ANALYSIS = auto() # 人物分析：性格、外貌、是谁
    SUMMARY = auto()            # 总结：概括、摘要
    TEMPORAL = auto()           # 时间相关：什么时候、后来
    GENERAL = auto()            # 通用查询
```

#### 2. 实现意图检测方法

在 `planner.py` 中修改 `RuleBasedPlanner` 类：

```python
from .models import QueryIntent

class RuleBasedPlanner:
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

    def _detect_intent(self, query: str) -> QueryIntent:
        """检测查询意图（优先级最高）"""
        for intent, keywords in self.INTENT_PATTERNS.items():
            if any(kw in query for kw in keywords):
                return intent
        return QueryIntent.GENERAL

    def _get_retrieval_intent(self, intent: QueryIntent) -> str:
        """根据意图返回检索意图"""
        mapping = {
            QueryIntent.CAUSAL_CHAIN: "causal_chain",
            QueryIntent.CHARACTER_ANALYSIS: "alias_resolution",
        }
        return mapping.get(intent, "scene_evidence")

    def _get_task_type(self, intent: QueryIntent, query: str) -> str:
        """根据意图返回任务类型"""
        if intent == QueryIntent.SUMMARY:
            return "summary"
        if intent == QueryIntent.CHARACTER_ANALYSIS:
            return "analysis"
        return "qa"
```

#### 3. 重构 plan 方法

```python
def plan(
    self,
    query: str,
    scope: Scope,
    history: list[ConversationTurn],
    *,
    multimodal: bool = False,
) -> tuple[PlannerOutput, MemoryState]:
    memory = self.infer_memory(history, scope)

    # 1. 检测意图（优先级最高）
    intent = self._detect_intent(query)

    # 2. 根据意图确定基础检索目标
    retrieval_targets = list(self.INTENT_TARGETS.get(intent, ["chapter_chunks"]))

    # 3. 人名关键词作为辅助增强（不覆盖意图决策）
    person_keywords = ("韩立", "张铁", "墨大夫", "舞岩", "韩胖子", "三叔")
    if any(kw in query for kw in person_keywords) and intent != QueryIntent.CHARACTER_ANALYSIS:
        # 因果/事实问题：补充 character_card 用于上下文，但不优先
        if "character_card" not in retrieval_targets:
            retrieval_targets.append("character_card")

    # 4. 其他辅助逻辑
    if "瓶子" in query or "后来" in query:
        if "recent_plot" not in retrieval_targets:
            retrieval_targets.append("recent_plot")

    if multimodal:
        retrieval_targets = ["vision_parse", *retrieval_targets]

    retrieval_intent = self._get_retrieval_intent(intent)

    return PlannerOutput(
        task_type=self._get_task_type(intent, query),
        retrieval_needed=True,
        retrieval_targets=list(dict.fromkeys(retrieval_targets)),
        retrieval_intent=retrieval_intent,
        constraints=["grounded_answer", "cite_evidence", "no_spoiler_beyond_scope"],
        success_criteria=["answer_correct", "answer_grounded"],
    ), memory
```

### 对比示例

| 查询 | 旧行为 | 新行为 |
|------|--------|--------|
| "韩立为什么参加测试" | character_card → chapter_chunks | event_timeline → chapter_chunks → character_card |
| "韩立是谁" | character_card → chapter_chunks | character_card → chapter_chunks |
| "韩立的性格怎么样" | character_card → chapter_chunks | character_card → chapter_chunks |
| "韩立最后怎么样了" | character_card → chapter_chunks | event_timeline → recent_plot |

### 验收标准

- 查询"韩立为什么参加测试"返回 `event_timeline` 优先
- 查询"韩立是谁"仍返回 `character_card` 优先
- 现有测试用例 `planner_001` 通过

---

## 设计三：验证层简化

### 目标

移除 `uncertainty` 字段，统一使用 `confidence` 表示置信度，消除 `service.py:728-729` 的逻辑错误和概念混淆。

### 改动文件

| 文件 | 改动类型 | 说明 |
|------|---------|------|
| novel_system/models.py | 修改 | 更新 AskResponse 模型 |
| novel_system/service.py | 修改 | 删除错误逻辑，统一使用 confidence |
| novel_system/tracing.py | 修改 | 更新 AskTrace 模型 |

### 详细设计

#### 1. 更新 AskResponse 模型

在 `models.py` 中修改：

```python
class AskResponse(BaseModel):
    planner: PlannerOutput
    answer: str
    evidence: list[EvidenceItem]
    confidence: Literal["low", "medium", "high"] = Field(
        description="答案置信度：high=高置信度，low=低置信度"
    )
    scope: Scope
    memory: dict[str, Any]
    warnings: list[APIWarning]
    trace: Optional[AskTrace] = None

    # 向后兼容（已弃用）
    uncertainty: Optional[Literal["low", "medium", "high"]] = Field(
        default=None,
        deprecated=True,
        description="已弃用，请使用 confidence 字段"
    )
```

#### 2. 修改 service.py 验证逻辑

删除错误代码（原 728-731 行）：

```python
# 删除以下错误代码：
# if validation_result.confidence == "high":
#     uncertainty = "high"
# elif validation_result.confidence == "medium" and uncertainty == "low":
#     uncertainty = "medium"
```

新增正确逻辑：

```python
# 直接使用 validation_result 的置信度
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

#### 3. 向后兼容处理

添加转换函数：

```python
def _compute_deprecated_uncertainty(confidence: str) -> str:
    """向后兼容：将 confidence 转换为旧 uncertainty 格式"""
    mapping = {"high": "low", "medium": "medium", "low": "high"}
    return mapping[confidence]
```

响应构建：

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

#### 4. 更新 AskTrace 模型

在 `tracing.py` 中修改：

```python
class AskTrace(BaseModel):
    trace_id: str
    book_id: str
    session_id: Optional[str]
    timestamp: datetime
    query_rewrite: QueryRewriteTrace
    planner: PlannerOutput
    retrieval: RetrievalTrace
    evidence_count: int
    evidence_spans: list[str]
    confidence: Literal["low", "medium", "high"]  # 替代 uncertainty
    total_duration_ms: float
    memory_state: dict[str, Any]
```

### 迁移路径

1. **阶段 3.1**：添加 `confidence` 字段，保留 `uncertainty` 并标记弃用
2. **阶段 3.2**：更新内部逻辑统一使用 `confidence`
3. **阶段 3.3**（后续版本）：移除 `uncertainty` 字段

### 验收标准

- `confidence="high"` 时，答案质量确实较高
- 响应中同时包含 `confidence` 和 `uncertainty`，且两者关系正确（互为反向）
- 现有 API 消费者仍可正常工作
- `validation_result.confidence == "high"` 不再导致错误的低置信度输出

---

## 实施顺序

按模块独立实施，每个模块完成后进行验证：

```
阶段 1: 检索层重构
    ↓ 验证通过
阶段 2: Planner 意图优先路由
    ↓ 验证通过
阶段 3: 验证层简化
    ↓ 验证通过
完成
```

---

## 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| jieba 分词效果不理想 | 检索质量提升有限 | 保留字符级回退，可切换回原方案 |
| 意图检测遗漏边界情况 | 路由错误 | 新增测试用例覆盖边界场景 |
| API 兼容性问题 | 现有客户端报错 | 保留 uncertainty 字段，添加弃用警告 |

---

## 验收测试用例

| 用例 ID | 类型 | 验证内容 |
|---------|------|---------|
| qa_001 | QA | "韩立参加七玄门测试的原因" 召回正确文档 |
| qa_003 | QA | "韩立与张铁的结果" 召回正确文档 |
| planner_001 | Planner | "韩立为什么参加测试" 返回 event_timeline 优先 |
| validation_001 | Validator | 高置信度答案对应 confidence="high" |
