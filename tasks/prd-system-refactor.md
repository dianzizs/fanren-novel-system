# PRD: 小王一号系统重构

## Introduction

本 PRD 基于四份审计报告（Claude 4.6 Opus / Codex 5.3 / GPT 5.4 / GPT 5.4 thinking）的汇总，修复运行时崩溃、核心功能失效、架构冗余等问题，共 5 个 Phase。

**问题概述：**
- P0 崩溃：SemanticScorer 从未工作、TF-IDF 返回错误文档、debug=true 时崩溃
- P1 退化：Validator 误报率极高、重试未实现、fallback 硬编码
- 架构问题：service.py 1951 行 God Object、双索引管道并存、别名映射 4+ 文件重复

## Goals

1. 修复所有 P0 运行时崩溃，使 debug=true 正常工作
2. 修复 P1 功能退化，使语义评分、TF-IDF 检索、Validator 正常工作
3. 清理架构冗余，将 service.py 拆分为独立服务模块
4. 统一别名映射、索引管道、评测管道
5. 删除死代码，补充关键测试

## User Stories

---

### Phase 1: P0 Bug 修复

#### US-001: 修复 SemanticScorer 属性访问错误
**Description:** 作为系统，需要正确访问 RetrievalHit 的文本内容，以便语义评分不再恒为 0.5。

**文件:** `novel_system/semantic_scorer.py:187-192`

**当前问题:**
```python
# 错误代码
text = getattr(hit, 'text', None)  # 永远返回 None
chunk_id = getattr(hit, 'chunk_id', None)  # 永远返回 None
```

**修复方案:**
```python
# 正确代码
text = hit.document.get("text", "")
chunk_id = hit.document.get("id", "")
```

**Acceptance Criteria:**
- [ ] `semantic_scorer.py` 中属性访问改为从 `hit.document` 字典获取
- [ ] 编写单元测试验证语义分数不再是固定 0.5
- [ ] 测试命令：`conda run -n chaishu python -m pytest tests/test_semantic_scorer.py -v`

---

#### US-002: 修复 TF-IDF scope 过滤索引对齐
**Description:** 作为系统，需要确保 scope 过滤后 docs 与 matrix 索引对齐，返回正确的文档。

**文件:** `novel_system/search/orchestrator.py:49-64, 134, 139`

**当前问题:**
scope 过滤后，docs 列表被筛选，但 TF-IDF matrix 索引仍指向原始文档，导致返回错误文档。

**修复方案:**
```python
# 方案 A: 过滤后重建 matrix
filtered_docs = [d for d in docs if _in_scope(d, scope)]
# 重建 TF-IDF matrix 基于过滤后的 docs
self._rebuild_tfidf_matrix(filtered_docs)

# 方案 B: 维护索引映射
# 过滤前记录原始索引，过滤后用映射转换
```

**Acceptance Criteria:**
- [ ] scope 过滤后返回的文档确实属于指定章节范围
- [ ] 编写测试用例：scope=[1,3] 时返回的文档 chapter 在 1-3 范围内
- [ ] 测试命令：`conda run -n chaishu python -m pytest tests/test_tfidf_retrieval.py -v`

---

#### US-003: 修复 `_in_scope` 范围语义
**Description:** 作为系统，需要正确处理章节范围语义，scope=[1,5] 应包含 chapter 2/3/4。

**文件:** `novel_system/search/orchestrator.py` 的 `_in_scope` 方法

**当前问题:**
```python
# 错误代码：[1,5] 被当作枚举，只匹配 1 和 5
return chapter in chapters
```

**修复方案:**
```python
# 正确代码：[1,5] 表示区间 1-5
if len(chapters) == 2:
    return min(chapters) <= chapter <= max(chapters)
else:
    return chapter in chapters
```

**Acceptance Criteria:**
- [ ] `_in_scope([1,5], 2)` 返回 True
- [ ] `_in_scope([1,5], 3)` 返回 True
- [ ] `_in_scope([1,5], 6)` 返回 False
- [ ] 添加单元测试覆盖范围语义

---

#### US-004: 修复 ContinuationTrace 字段名
**Description:** 作为系统，需要正确构造 ContinuationTrace，避免 debug=true 时崩溃。

**文件:** `novel_system/service.py` 中 `continue_story()` 构造 trace 的位置

**当前问题:**
```python
# 错误代码
ContinuationTrace(uncertainty=...)  # 字段名不匹配
```

**修复方案:**
```python
# 正确代码
ContinuationTrace(confidence=...)
```

**Acceptance Criteria:**
- [ ] 搜索所有 `uncertainty=` 并改为 `confidence=`
- [ ] debug=true 调用 continue_story 端点不崩溃
- [ ] 手动验证：`curl -X POST "http://localhost:8000/api/books/{book_id}/continue" -d '{"query": "...", "debug": true}'`

---

#### US-005: 修复 ContinuationResponse confidence 赋值
**Description:** 作为系统，需要从验证结果正确计算 confidence 值，而不是永远返回 "medium"。

**文件:** `novel_system/service.py` 中 `continue_story()` 构造 response 的位置

**当前问题:**
confidence 值硬编码为 "medium"，未使用验证结果。

**修复方案:**
```python
# 根据验证结果计算 confidence
if validation_result.has_critical_issues:
    confidence = "low"
elif validation_result.has_warnings:
    confidence = "medium"
else:
    confidence = "high"
```

**Acceptance Criteria:**
- [ ] confidence 值根据验证结果动态计算
- [ ] 有严重问题时 confidence 为 "low"
- [ ] 无问题时 confidence 为 "high"

---

### Phase 2: 检索质量提升

#### US-006: 修复别名匹配方向
**Description:** 作为系统，需要正确匹配别名，避免短别名误匹配。

**文件:** `novel_system/search/orchestrator.py:99`

**当前问题:**
```python
# 错误代码：query 包含在 value 中，方向反了
if query in value:
```

**修复方案:**
```python
# 正确代码：value（别名）在 query 中
if value in query:
    # 但需要处理短别名问题，如单字"韩"
    if len(value) == 1:
        # 使用分词匹配
        pass
```

**Acceptance Criteria:**
- [ ] 别名匹配方向正确
- [ ] 短别名（单字）不误匹配
- [ ] 添加测试用例验证

---

#### US-007: 统一别名映射
**Description:** 作为开发者，需要将分散在 4+ 文件中的别名映射统一到单一数据源。

**涉及文件:**
- `novel_system/planner.py`
- `novel_system/entity_extractor.py`
- `novel_system/validator.py`
- `novel_system/indexing.py`

**修复方案:**
1. 新建 `novel_system/aliases.py`
2. 提取所有别名定义（`ALIAS_EXPANSIONS` 等）
3. 各模块改为 `from novel_system.aliases import ALIAS_MAP`

**Acceptance Criteria:**
- [ ] 创建 `novel_system/aliases.py` 包含所有别名定义
- [ ] 4 个文件中的别名定义已删除，改为导入
- [ ] `conda run -n chaishu python -c "from novel_system.aliases import ALIAS_MAP"` 成功

---

#### US-008: 改进 `_sparse_fallback`
**Description:** 作为系统，需要在 sparse fallback 时过滤停用词，提高匹配质量。

**文件:** `novel_system/search/orchestrator.py:157`

**修复方案:**
```python
# 过滤停用词
STOPWORDS = {"的", "是", "了", "在", "和", "有", "不", "这", "那"}
filtered_query = "".join([w for w in query if w not in STOPWORDS])
# 或使用 jieba 分词后匹配
```

**Acceptance Criteria:**
- [ ] sparse fallback 不再匹配纯停用词
- [ ] 添加测试用例验证停用词过滤

---

#### US-009: 实现跨 target rerank
**Description:** 作为系统，需要对多 target 结果统一排序，而不是简单拼接。

**文件:** `novel_system/search/orchestrator.py` 的 `retrieve()` 方法

**修复方案:**
```python
# 收集所有 target 结果
all_results = []
for target in targets:
    results = self._retrieve_single(target)
    all_results.extend(results)

# 归一化分数后统一排序
normalized = self._normalize_scores(all_results)
sorted_results = sorted(normalized, key=lambda x: x.score, reverse=True)
return sorted_results[:top_k]
```

**Acceptance Criteria:**
- [ ] 多 target 检索结果按分数统一排序
- [ ] 添加测试验证排序正确性

---

#### US-010: 修复 profiles.py 配置生效
**Description:** 作为系统，需要让 SearchProfile 配置实际生效，特别是 `text_field` 配置。

**文件:**
- `novel_system/search/profiles.py`
- `novel_system/search/orchestrator.py`

**当前问题:**
`character_card` 的 `text_field` 配置为 `"description"`，但实际字段名为 `"text"`。

**修复方案:**
```python
# profiles.py
SearchProfile(
    name="character_card",
    text_field="text",  # 修正
    # ...
)

# orchestrator.py 中使用配置
text = doc.get(profile.text_field, "")
```

**Acceptance Criteria:**
- [ ] `character_card` 的 `text_field` 改为 `"text"`
- [ ] orchestrator 从 profile 读取 `id_field`, `text_field` 配置
- [ ] 添加测试验证配置生效

---

### Phase 3: Validator 降噪 + service.py 拆分

#### US-011: SpoilerGuard 降噪
**Description:** 作为系统，需要降低 SpoilerGuard 误报率，不再对正常叙事报警。

**文件:** `novel_system/validator.py:816-825`

**修复方案:**
1. 移除过于通用的关键词：`"成功"`, `"发现"`, `"终于"`, `"获得"`
2. 要求多个关键词同时命中才触发
3. 去重 `FUTURE_KEYWORDS` 和 `PLOT_TWIST_KEYWORDS` 重叠词

```python
# 修改关键词列表
FUTURE_KEYWORDS = [
    # 移除过于通用的词
    # "成功", "发现", "终于", "获得"
]

# 多关键词触发
def _check_spoiler(text):
    hits = [kw for kw in FUTURE_KEYWORDS if kw in text]
    return len(hits) >= 2  # 至少 2 个关键词
```

**Acceptance Criteria:**
- [ ] 移除至少 4 个过于通用的关键词
- [ ] 改为需要 >= 2 个关键词才触发
- [ ] 添加测试：正常叙事不触发报警

---

#### US-012: check_world_boundary 降噪
**Description:** 作为系统，需要降低 check_world_boundary 误报率。

**文件:** `novel_system/validator.py:736-751`

**修复方案:**
```python
# 方案 A: 只检查核心实体/动作对
CORE_ENTITIES = {"韩立", "瓶灵", "掌天瓶"}
# 只检查包含核心实体的规则

# 方案 B: 增加 LLM 判断（可选）
```

**Acceptance Criteria:**
- [ ] `check_world_boundary` 不再对 "修士" 等通用词报警
- [ ] 误报率显著降低

---

#### US-013: 修复 `_check_appearance` 双重计数
**Description:** 作为系统，需要避免颜色矛盾被报告两次。

**文件:** `novel_system/validator.py:576-596`

**修复方案:**
合并 `entity_extractor.check_entity_consistency()` 和 `_check_color_consistency()` 为单一检查。

**Acceptance Criteria:**
- [ ] 同一颜色矛盾只报告一次
- [ ] 添加测试验证

---

#### US-014: Validator 结果阻断
**Description:** 作为系统，需要让验证结果实际影响最终输出。

**文件:** `novel_system/service.py` 调用链

**修复方案:**
```python
# 当验证发现严重问题时
if validation_result.has_critical_issues:
    response.confidence = "low"
    response.warnings = validation_result.critical_issues
    # 或拒绝返回结果
```

**Acceptance Criteria:**
- [ ] 严重问题会降低 confidence
- [ ] 警告会附加到 response.warnings
- [ ] 添加集成测试验证

---

#### US-015: 创建 AnswerService
**Description:** 作为开发者，需要将 ask 流程从 service.py 拆分为独立模块。

**文件:**
- 新建 `novel_system/answer_service.py`
- 修改 `novel_system/service.py`

**修复方案:**
```python
# novel_system/answer_service.py
class AnswerService:
    def __init__(self, ...): ...
    async def ask(self, book_id: str, query: str, ...) -> AnswerResponse: ...

# service.py 保留为 facade
async def ask(*args, **kwargs):
    return await answer_service.ask(*args, **kwargs)
```

**Acceptance Criteria:**
- [ ] 创建 `novel_system/answer_service.py`
- [ ] ask 流程逻辑已迁移
- [ ] service.py 保留为 facade
- [ ] 现有测试通过

---

#### US-016: 创建 ContinuationService
**Description:** 作为开发者，需要将 continue 流程从 service.py 拆分为独立模块。

**文件:**
- 新建 `novel_system/continuation_service.py`
- 修改 `novel_system/service.py`

**修复方案:**
```python
# novel_system/continuation_service.py
class ContinuationService:
    def __init__(self, ...): ...
    async def continue_story(self, book_id: str, query: str, ...) -> ContinuationResponse: ...
```

**Acceptance Criteria:**
- [ ] 创建 `novel_system/continuation_service.py`
- [ ] continue 流程逻辑已迁移
- [ ] service.py 保留为 facade
- [ ] 现有测试通过

---

#### US-017: 创建 GraphService
**Description:** 作为开发者，需要将图谱相关逻辑从 service.py 拆分为独立模块。

**文件:**
- 新建 `novel_system/graph_service.py`
- 修改 `novel_system/service.py`

**修复方案:**
```python
# novel_system/graph_service.py
class GraphService:
    def __init__(self, ...): ...
    def get_interactive_graph(self, ...): ...

# 迁移行 79-193 的图相关常量
```

**Acceptance Criteria:**
- [ ] 创建 `novel_system/graph_service.py`
- [ ] 图相关逻辑和常量已迁移
- [ ] service.py 保留为 facade
- [ ] 现有测试通过

---

#### US-018: 实现 LLM 重试
**Description:** 作为系统，需要实现已定义但未使用的重试机制。

**文件:** `novel_system/llm.py`

**当前问题:**
`MAX_RETRIES=3` 和 `RETRY_DELAYS` 已定义，但 `chat()` 中无重试循环。

**修复方案:**
```python
async def chat(self, messages, **kwargs):
    for attempt in range(MAX_RETRIES):
        try:
            return await self._call_api(messages, **kwargs)
        except (RateLimitError, TimeoutError) as e:
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(RETRY_DELAYS[attempt])
            else:
                raise
```

**Acceptance Criteria:**
- [ ] `chat()` 方法包含重试循环
- [ ] 使用 `MAX_RETRIES` 和 `RETRY_DELAYS`
- [ ] 添加测试验证重试逻辑

---

#### US-019: 修复 `_fallback_analysis()` 硬编码
**Description:** 作为系统，需要将硬编码的 fallback 改为基于检索结果的动态兜底。

**文件:** `novel_system/service.py:1598-1603`

**当前问题:**
```python
# 硬编码内容
return "韩立发现瓶子..."  # 无论查询什么都返回固定文本
```

**修复方案:**
```python
# 基于检索结果的动态兜底
if retrieval_results:
    return self._synthesize_from_results(retrieval_results)
return "抱歉，未能找到相关信息。"
```

**Acceptance Criteria:**
- [ ] `_fallback_analysis()` 不再返回硬编码文本
- [ ] 基于检索结果生成兜底答案
- [ ] 添加测试验证

---

### Phase 4: 评测管道修复 + 工程化

#### US-020: 删除 run_eval.py 硬编码
**Description:** 作为开发者，需要删除评测脚本中的硬编码特殊 case。

**文件:** `scripts/run_eval.py`

**修复方案:**
删除 `product_002` 等硬编码逻辑，改为通用处理。

**Acceptance Criteria:**
- [ ] 无硬编码测试用例 ID
- [ ] 评测脚本能处理通用测试用例

---

#### US-021: 添加评测 KeyError 保护
**Description:** 作为开发者，需要添加 category 字段的 KeyError 保护。

**文件:** `scripts/run_eval.py`, `eval_runner_template.py`

**修复方案:**
```python
category = case.get("category", "unknown")  # 使用 get 默认值
```

**Acceptance Criteria:**
- [ ] 缺少 category 字段不崩溃
- [ ] 添加 per-case 异常捕获

---

#### US-022: 统一评测输出路径
**Description:** 作为开发者，需要统一评测输出路径。

**文件:** `scripts/run_eval.py`

**当前问题:**
`eval_results/` vs `eval_output/` 路径分裂。

**修复方案:**
统一为 `eval_output/`。

**Acceptance Criteria:**
- [ ] 所有评测输出使用统一路径
- [ ] 无路径分裂问题

---

#### US-023: 删除死代码
**Description:** 作为开发者，需要删除已识别的死代码。

**涉及文件:**
| 文件 | 删除内容 |
|------|---------|
| `search/base.py` | `SparseBackend`, `DenseBackend` Protocol |
| `search/base.py` | `RetrievalCandidate` |
| `validator.py:52-58` | `CharacterIssue` model |
| `validator.py:689-715` | `_extract_appearance_keywords`, `_find_contradiction` |
| `planner.py:48,50` | `SCOPE_HINT_RE`, `PRONOUN_RE` |
| `planner.py:215` | `lowered = query.lower()` |
| `eval_runner_template.py:28` | `contains_all()` |
| `semantic_scorer.py:307,310` | `_scorer` 全局单例 + `get_scorer()` |

**Acceptance Criteria:**
- [ ] 上述死代码已删除
- [ ] `conda run -n chaishu python -m pytest tests/ -v` 通过
- [ ] 服务启动正常

---

#### US-024: 修正 requirements.txt
**Description:** 作为开发者，需要修正依赖配置。

**文件:** `requirements.txt`

**修复方案:**
1. 添加缺失依赖
2. 添加版本上限约束
3. 降低不合理的版本下限

**Acceptance Criteria:**
- [ ] 无缺失依赖
- [ ] 有版本上限约束
- [ ] `conda run -n chaishu pip install -r requirements.txt` 成功

---

#### US-025: 补充 semantic_scorer 单元测试
**Description:** 作为开发者，需要补充 semantic_scorer 的单元测试。

**文件:** `tests/test_semantic_scorer.py`

**Acceptance Criteria:**
- [ ] 测试文件存在
- [ ] 覆盖语义评分核心逻辑
- [ ] `conda run -n chaishu python -m pytest tests/test_semantic_scorer.py -v` 通过

---

#### US-026: 补充 llm 重试逻辑测试
**Description:** 作为开发者，需要补充 llm.py 重试逻辑的测试。

**文件:** `tests/test_llm_retry.py`

**Acceptance Criteria:**
- [ ] 测试文件存在
- [ ] 验证重试次数和延迟
- [ ] `conda run -n chaishu python -m pytest tests/test_llm_retry.py -v` 通过

---

### Phase 5: 索引管道统一 + 进阶优化

#### US-027: 完善 index_pipeline.py 接入
**Description:** 作为开发者，需要完善新索引管道并接入 service 层。

**文件:**
- `novel_system/index_pipeline.py`
- `novel_system/service.py`

**Acceptance Criteria:**
- [ ] index_pipeline 完全替代 indexing.py 功能
- [ ] service 层使用新管道
- [ ] 现有测试通过

---

#### US-028: 删除旧索引管道
**Description:** 作为开发者，需要在确认新管道稳定后删除旧管道。

**文件:** `novel_system/indexing.py`

**Acceptance Criteria:**
- [ ] `novel_system/indexing.py` 已删除
- [ ] 无引用该文件的其他代码
- [ ] 所有测试通过

---

#### US-029: 统一 Planner 路由
**Description:** 作为开发者，需要合并 if-else 链和 `_detect_intent()` 为单一路由表。

**文件:** `novel_system/planner.py:216-308`

**修复方案:**
```python
# 创建路由表
ROUTE_TABLE = {
    "人物": Intent.CHARACTER,
    "什么": Intent.FACT,
    # ...
}

def _detect_intent(self, query: str) -> Intent:
    for pattern, intent in ROUTE_TABLE.items():
        if pattern in query:
            return intent
    return Intent.GENERAL
```

**Acceptance Criteria:**
- [ ] 单一路由表驱动
- [ ] `retrieval_intent` 字段被下游消费
- [ ] 现有测试通过

---

#### US-030: 注入 rewrite_note 到 LLM context
**Description:** 作为系统，需要将 rewrite_note 注入 LLM messages。

**文件:** `novel_system/service.py:1431-1433`

**当前问题:**
`rewrite_note` 计算后未注入 LLM messages。

**修复方案:**
```python
# 在 LLM 调用前注入
if rewrite_note:
    messages.append({"role": "system", "content": rewrite_note})
```

**Acceptance Criteria:**
- [ ] rewrite_note 注入 LLM context
- [ ] 添加测试验证

---

## Functional Requirements

### FR-1: Phase 1 - P0 Bug 修复
- FR-1.1: SemanticScorer 必须从 `hit.document` 字典获取 text 和 id
- FR-1.2: TF-IDF scope 过滤后必须保持 docs 与 matrix 索引对齐
- FR-1.3: `_in_scope([min,max], chapter)` 必须表示区间语义
- FR-1.4: ContinuationTrace 必须使用 `confidence` 字段名
- FR-1.5: ContinuationResponse confidence 必须根据验证结果动态计算

### FR-2: Phase 2 - 检索质量
- FR-2.1: 别名匹配必须是 `value in query` 方向
- FR-2.2: 别名映射必须统一到 `novel_system/aliases.py`
- FR-2.3: sparse fallback 必须过滤停用词
- FR-2.4: 多 target 检索必须统一排序
- FR-2.5: SearchProfile 配置必须被 orchestrator 使用

### FR-3: Phase 3 - Validator + 架构
- FR-3.1: SpoilerGuard 必须需要 >= 2 个关键词才触发
- FR-3.2: check_world_boundary 必须只检查核心实体
- FR-3.3: service.py 必须拆分为 AnswerService/ContinuationService/GraphService
- FR-3.4: LLM 调用必须实现重试机制
- FR-3.5: Validator 结果必须影响最终输出

### FR-4: Phase 4 - 工程化
- FR-4.1: 评测脚本必须无硬编码测试用例
- FR-4.2: 必须删除所有死代码
- FR-4.3: requirements.txt 必须有版本上限约束

### FR-5: Phase 5 - 进阶优化
- FR-5.1: 必须删除旧索引管道 indexing.py
- FR-5.2: Planner 必须使用单一路由表
- FR-5.3: rewrite_note 必须注入 LLM context

## Non-Goals (Out of Scope)

- 不修改 API 接口签名
- 不修改前端代码
- 不引入新的外部依赖（除必要的缺失依赖）
- 不实现 Claim-level validation（GPT 5.4 建议，超出当前范围）
- 不实现 Answer Composer（GPT 5.4 建议，超出当前范围）
- 不处理 pickle 反序列化安全问题（需要更大范围的架构改动）
- 不处理线程安全问题（需要更大范围的架构改动）

## Technical Considerations

### 环境约束
- 必须使用 conda chaishu 环境
- Python 版本需与现有项目兼容
- 测试命令：`conda run -n chaishu python -m pytest tests/ -v`

### 代码风格
- 遵循现有项目风格
- 不改变非必要的格式
- 类型提示保持一致

### 验证方法
- 每个 Phase 完成后运行完整测试套件
- Phase 1 后手动验证 debug=true 不崩溃
- Phase 2 后验证检索返回正确章节
- Phase 3 后验证 Validator 不误报

## Success Metrics

| 指标 | 当前值 | 目标值 |
|------|--------|--------|
| debug=true 崩溃率 | 100% | 0% |
| 语义评分恒定 0.5 | 是 | 否 |
| TF-IDF scope 错误率 | 高 | 0% |
| Validator 误报率 | 极高 | < 10% |
| service.py 行数 | 1951 | < 500 (facade) |
| 死代码量 | 多处 | 0 |
| 测试覆盖率 | 低 | 提升 50% |

## Open Questions

1. **短别名处理策略**：单字符别名（如"韩"）是否需要分词匹配？阈值如何确定？
2. **Validator 阻断策略**：严重问题是否应完全阻断输出，还是仅降低 confidence？
3. **LLM 重试异常类型**：哪些异常应该重试？RateLimit/Timeout 之外是否还有其他？
4. **旧管道迁移时机**：index_pipeline.py 稳定运行多久后可删除 indexing.py？
5. **评测维度**：审计报告称宣称 9 个维度仅有 5 个，是否需要补齐缺失维度？

## Appendix: 文件改动索引

| 文件 | 行数 | 改动 Phase |
|------|------|-----------|
| `novel_system/service.py` | 1951 | P1, P3, P4 |
| `novel_system/semantic_scorer.py` | 328 | P1 |
| `novel_system/search/orchestrator.py` | ~200 | P1, P2 |
| `novel_system/validator.py` | 1009 | P3 |
| `novel_system/planner.py` | 309 | P2, P5 |
| `novel_system/retrieval.py` | 65 | P2 |
| `novel_system/llm.py` | 70 | P3 |
| `novel_system/indexing.py` | 652 | P5（删除） |
| `novel_system/index_pipeline.py` | — | P5 |
| `novel_system/aliases.py` | — | P2（新建） |
| `novel_system/answer_service.py` | — | P3（新建） |
| `novel_system/continuation_service.py` | — | P3（新建） |
| `novel_system/graph_service.py` | — | P3（新建） |
| `scripts/run_eval.py` | — | P4 |
| `requirements.txt` | — | P4 |
