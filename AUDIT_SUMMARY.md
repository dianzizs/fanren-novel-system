# 小王一号 — 四份审计报告汇总与重构方案

> 汇总日期: 2026-04-14
> 审计来源: Claude 4.6 Opus / Codex 5.3 / GPT 5.4 / GPT 5.4 thinking
> 审计范围: 全部源码（novel_system/、scripts/、tests/）、文档、评测用例、依赖配置

---

## 一、四份报告共识（17 项）

### P0 — 运行时崩溃 / 核心功能失效

| # | 问题 | 涉及文件 | 四份报告均提及 |
|---|------|---------|--------------|
| 1 | SemanticScorer 属性访问错误：`getattr(hit, 'text')` 永远为 None，语义评分恒为 0.5，从未工作 | `semantic_scorer.py:187-192` | ✓ |
| 2 | TF-IDF scope 过滤后 docs 与 matrix 索引不对齐，返回错误文档 | `search/orchestrator.py:49-64,134,139` | ✓ |
| 3 | ContinuationTrace 构造传 `uncertainty=` 但字段名为 `confidence`，debug=true 时崩溃 | `service.py` → `tracing.py` / `models.py` | ✓ |

### P1 — 功能严重退化

| # | 问题 | 涉及文件 |
|---|------|---------|
| 4 | SpoilerGuard 误报率极高：常见词（"成功"、"发现"、"终于"）触发 | `validator.py:816-825` |
| 5 | `check_world_boundary` 误报率极高：从规则提取 2-4 字词，"修士"必然命中 | `validator.py:736-751` |
| 6 | `_check_appearance` 双重计数：颜色矛盾被报告两次 | `validator.py:576-596` |
| 7 | Validator 只报告不阻断：验证结果未影响最终输出 | `service.py` 调用链 |
| 8 | `_fallback_analysis()` 硬编码"韩立发现瓶子"，无论查询什么都返回固定文本 | `service.py:1598-1603` |
| 9 | LLM 重试未实现：`MAX_RETRIES=3` 和 `RETRY_DELAYS` 已定义但无重试循环 | `llm.py` |

### 架构 / 冗余问题

| # | 问题 | 涉及文件 |
|---|------|---------|
| 10 | service.py 1951 行 God Object，零单元测试 | `service.py` |
| 11 | 双索引管道并存：旧 `indexing.py` + 新 `index_pipeline.py`，新管道未接入 | 两个文件 |
| 12 | 别名映射在 4+ 文件中重复定义 | `planner.py`, `entity_extractor.py`, `validator.py`, `indexing.py` |
| 13 | 人名提取逻辑三处重复 | `entity_extractor.py`, `indexing.py`, `validator.py` |
| 14 | Planner 双层路由冲突：if-else 链短路 `_detect_intent()` | `planner.py:216-308` |
| 15 | 评测管道：硬编码特殊 case、schema 分裂、维度缺失（宣称 9 个仅有 5 个） | `scripts/run_eval.py`, `eval_runner_template.py` |
| 16 | 大量死代码：`SparseBackend`/`DenseBackend` Protocol、`CharacterIssue`、`contains_all()` 等 | 多文件 |
| 17 | `requirements.txt` 缺失依赖、版本下限过高、无上限约束 | `requirements.txt` |

---

## 二、各报告独特发现

### Claude 4.6 Opus 独有
- 强调**接口契约**方法论：`RetrievalHit` dataclass 与 SemanticScorer 期望接口不匹配是系统性根因
- `rewrite_note` 计算后未注入 LLM messages（`service.py:1431-1433`）
- `_extract_recent_context()` 返回值仅作布尔判断，提取的上下文词汇未追加到 query
- pickle 反序列化安全隐患（`indexing.py`）
- 线程安全问题：daemon thread 修改 `self.repo._cache` 无锁（`service.py:440-445,539`）

### Codex 5.3 独有
- **`_in_scope` 范围语义 bug**：`[1,5]` 被当作枚举而非区间，chapter 2/3/4 被漏掉
- `character_card` 的 `text_field` 配置为 `"description"` 但实际字段名为 `"text"`
- `retrieval_intent` 字段在 Planner 中设置但下游从未消费
- 评测 dashboard 路径分裂（`eval_results/` vs `eval_output/`）
- 提出 12 个 MVP patch 的具体代码修改方案

### GPT 5.4 独有
- **character_card 过度优先**作为检索质量退化的根因分析
- 缺少跨 target rerank 机制：多 target 结果简单拼接无统一排序
- Answer Composer 概念：当前答案生成是"复制粘贴"而非合成
- Claim-level validation：建议将答案拆分为独立声明逐条验证
- `get_interactive_graph()` ~265 行方法职责过多

### GPT 5.4 thinking
- 仅有 .docx 格式，无法程序化读取，内容未纳入本次汇总

---

## 三、冗余清理清单

### 3.1 死代码删除

| 文件 | 删除内容 | 原因 |
|------|---------|------|
| `search/base.py` | `SparseBackend`, `DenseBackend` Protocol | 无实现类、无引用 |
| `search/base.py` | `RetrievalCandidate` | 仅测试中实例化一次，orchestrator 用裸 dict |
| `validator.py:52-58` | `CharacterIssue` model | 从未实例化 |
| `validator.py:689-715` | `_extract_appearance_keywords`, `_find_contradiction` | 从未调用 |
| `planner.py:48,50` | `SCOPE_HINT_RE`, `PRONOUN_RE` | 定义后从未使用 |
| `planner.py:215` | `lowered = query.lower()` | 计算后从未使用 |
| `eval_runner_template.py:28` | `contains_all()` | 定义后从未调用 |
| `semantic_scorer.py:307,310` | `_scorer` 全局单例 + `get_scorer()` | 从未被 service 层使用 |
| `search/__init__.py` | docstring 中声称的 sparse/dense/hybrid/rerank 子模块 | 文件不存在 |

### 3.2 重复代码合并

| 重复项 | 当前分布 | 合并目标 |
|--------|---------|---------|
| 别名映射 (ALIAS_EXPANSIONS 等) | `planner.py`, `entity_extractor.py`, `validator.py`, `indexing.py` | → 新建 `novel_system/aliases.py` 单一数据源 |
| 人名提取逻辑 | `entity_extractor.py`, `indexing.py`, `validator.py` | → `entity_extractor.py` 统一提供 |
| 颜色矛盾检测 | `entity_extractor.check_entity_consistency()` + `_check_color_consistency()` | → 合并为单一检查，消除双重计数 |

### 3.3 废弃管道清理

| 项目 | 处理方式 |
|------|---------|
| `indexing.py`（旧管道） | 待 `index_pipeline.py` 完全接入后删除 |
| `novel_heuristics.py` 中 `heuristic_answer()` | 始终返回 None，删除占位符 |
| `service.py:1598-1603` `_fallback_analysis()` 硬编码内容 | 替换为基于检索结果的动态兜底 |

---

## 四、分阶段重构方案

### Phase 1：P0 Bug 修复（预计改动 ~200 行）

目标：修复运行时崩溃和核心功能失效，不改架构。

**1.1 修复 SemanticScorer 属性访问**
- 文件：`semantic_scorer.py:187-192`
- 改法：`hit.document["text"]` 替代 `getattr(hit, 'text')`；`hit.document.get("id", "")` 替代 `getattr(hit, 'chunk_id')`
- 验证：单元测试确认语义分数不再恒为 0.5

**1.2 修复 TF-IDF scope 索引对齐**
- 文件：`search/orchestrator.py:49-64`
- 改法：scope 过滤后重建 TF-IDF matrix，或在过滤前记录原始索引映射
- 验证：构造 scope=[1,3] 的测试用例，确认返回文档属于指定章节

**1.3 修复 `_in_scope` 范围语义**（Codex 5.3 独有发现）
- 文件：`search/orchestrator.py` 的 `_in_scope` 方法
- 改法：将 `chapter in chapters` 改为 `min(chapters) <= chapter <= max(chapters)` 或使用 `range()`
- 验证：scope=[1,5] 应包含 chapter 2/3/4

**1.4 修复 ContinuationTrace 字段名**
- 文件：`service.py` 中 `continue_story()` 构造 trace 的位置
- 改法：`uncertainty=` → `confidence=`
- 验证：`debug=true` 调用 continue_story 不再崩溃

**1.5 修复 ContinuationResponse confidence 赋值**
- 文件：`service.py` 中 `continue_story()` 构造 response 的位置
- 改法：从验证结果正确计算 confidence 值
- 验证：返回的 confidence 不再永远是 "medium"

### Phase 2：检索质量提升（预计改动 ~400 行）

目标：让检索和评分真正工作。

**2.1 别名匹配方向修正**
- 文件：`search/orchestrator.py:99`
- 改法：`query in value` → `value in query`（或更精确的分词匹配）
- 注意：短别名（如单字"韩"）需要额外处理

**2.2 别名映射统一**
- 新建 `novel_system/aliases.py`，从 `planner.py`, `entity_extractor.py`, `validator.py`, `indexing.py` 中提取所有别名定义
- 各模块改为 `from novel_system.aliases import ALIAS_MAP`

**2.3 `_sparse_fallback` 改进**
- 文件：`search/orchestrator.py:157`
- 改法：过滤停用词（"的"、"是"、"了"等），或改用 jieba 分词后匹配

**2.4 跨 target rerank**（GPT 5.4 建议）
- 在 `SearchOrchestrator.retrieve()` 最终返回前，对所有 target 的结果做统一排序
- 可先用简单的 score 归一化 + 合并排序

**2.5 profiles.py 配置生效**
- 让 orchestrator 从 `SearchProfile` 读取 `id_field`, `text_field`, `exact_alias_fields`
- 修复 `character_card` 的 `text_field` 配置（`"description"` → `"text"`）

### Phase 3：Validator 降噪 + service.py 拆分（预计改动 ~600 行）

目标：降低误报率，拆分 God Object。

**3.1 SpoilerGuard 降噪**
- 移除过于通用的关键词（"成功"、"发现"、"终于"、"获得"）
- 去重 `FUTURE_KEYWORDS` 和 `PLOT_TWIST_KEYWORDS` 中的重叠词
- 改为需要多个关键词同时命中才触发

**3.2 `check_world_boundary` 降噪**
- 改为仅检查规则中的核心实体/动作对，而非所有 2-4 字词
- 或改为 LLM 判断（成本更高但准确）

**3.3 Validator 结果阻断**
- 在 `service.py` 中，当验证发现严重问题时实际影响输出（降低 confidence 或附加警告）

**3.4 service.py 拆分**
- 提取 `AnswerService`（ask 流程）→ `novel_system/answer.py`
- 提取 `ContinuationService`（continue 流程）→ `novel_system/continuation.py`
- 提取 `GraphService`（图谱相关）→ `novel_system/graph.py`
- `service.py` 保留为 facade，委托给上述模块
- 行 79-193 的图相关常量移入 `graph.py`

**3.5 LLM 重试实现**
- 文件：`llm.py`
- 利用已定义的 `MAX_RETRIES` 和 `RETRY_DELAYS`，在 `chat()` 中加入重试循环

### Phase 4：评测管道修复 + 工程化（预计改动 ~300 行）

**4.1 评测管道修复**
- 删除 `run_eval.py` 中 `product_002` 硬编码
- 添加 `category` 字段 KeyError 保护
- 添加 per-case 异常捕获
- 统一评测输出路径

**4.2 死代码清理**
- 按 §3.1 清单删除所有死代码

**4.3 requirements.txt 修正**
- 添加缺失依赖（`eval_runner_template` 或将其纳入项目）
- 调整版本约束（添加上限，降低不合理的下限）

**4.4 补充关键测试**
- `service.py` 的 `ask()` 和 `continue_story()` 集成测试
- `semantic_scorer.py` 单元测试
- `llm.py` 重试逻辑测试

### Phase 5：索引管道统一 + 进阶优化

**5.1 索引管道统一**
- 完善 `index_pipeline.py`，接入 service 层
- 迁移 `indexing.py` 中仍需要的逻辑
- 删除 `indexing.py`

**5.2 Planner 路由统一**
- 合并 if-else 链和 `_detect_intent()` 为单一路由表
- 让 `retrieval_intent` 字段被下游消费

**5.3 Answer Composer**（GPT 5.4 建议，可选）
- 将答案生成从简单 prompt 改为结构化合成
- 引入 `rewrite_note` 到 LLM context

---

## 五、验证方案

每个 Phase 完成后：

1. **单元测试**：`conda run -n chaishu python -m pytest tests/ -v`
2. **集成测试**：启动服务后用 curl 测试 ask / continue 端点
3. **评测回归**：`conda run -n chaishu python scripts/run_eval.py`（Phase 4 之后）
4. **手动验证**：
   - Phase 1 后：`debug=true` 调用 continue_story 不崩溃；语义分数不再恒为 0.5
   - Phase 2 后：scope 过滤返回正确章节文档；别名匹配不再误匹配
   - Phase 3 后：SpoilerGuard 不再对正常叙事报警

---

## 六、关键文件索引

| 文件 | 行数 | 改动阶段 |
|------|------|---------|
| `novel_system/service.py` | 1951 | P1, P3, P4 |
| `novel_system/semantic_scorer.py` | 328 | P1 |
| `novel_system/search/orchestrator.py` | ~200 | P1, P2 |
| `novel_system/validator.py` | 1009 | P3 |
| `novel_system/planner.py` | 309 | P2, P5 |
| `novel_system/retrieval.py` | 65 | P2 |
| `novel_system/llm.py` | 70 | P3 |
| `novel_system/indexing.py` | 652 | P5（删除） |
| `novel_system/index_pipeline.py` | — | P5 |
| `novel_system/entity_extractor.py` | — | P2 |
| `novel_system/search/base.py` | — | P4（清理） |
| `novel_system/search/profiles.py` | — | P2 |
| `scripts/run_eval.py` | — | P4 |
| `requirements.txt` | — | P4 |
