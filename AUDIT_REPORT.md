# 《fanren-novel-system 仓库深度审计报告》

**审计日期**：2026-04-14
**审计版本**：基于 commit 688f843 (后端优化完成)
**审计目标**：分析项目效果差的根因，给出可执行的改进方案

---

## 0. 文档摘要

### 项目真实状态概述

本项目是一个基于 FastAPI 构建的小说问答系统，宣称支持智能问答、情节续写、人物关系图谱、时间线生成等功能。经过深度代码审计，**该项目的真实定位是"功能骨架完整但效果链路未打通的 MVP 原型"**，而非 README 所暗示的"成熟可用的小说问答系统"。

### 当前最大问题

**核心问题是检索层极其简陋，导致整个系统"形似而神不似"。** 具体表现为：

1. **SearchOrchestrator 的 `_sparse_fallback` 方法仅实现字符级重叠计数**，完全没有真正的 BM25、TF-IDF 或稠密检索。这导致检索召回率和准确率都极低。

2. **Planner 的任务判定完全依赖硬编码关键词匹配**，无法理解语义意图，导致 retrieval_targets 路由错误频发。

3. **Validator 层存在严重的逻辑错误**——`validation_result.confidence == "high"` 时却将 `uncertainty` 设为 `"high"`，这是明显的代码 bug。

### 为什么"模块很多，但效果仍差"

项目创建了 Planner、Retrieval、Validator、Memory、Safety、Evaluation 等多个概念模块，**但每个模块都停留在"框架级实现"，缺乏真正决定效果的细节打磨**：

- Planner：有关键词匹配框架，但没有语义理解能力
- Retrieval：有接口抽象，但核心检索逻辑是字符计数
- Validator：有数据模型，但 groundedness 计算只是简单关键词覆盖
- Memory：有 MemoryState 类，但计算结果只用于渲染提示词，不真正影响检索
- Safety：有剧透防护概念，但检测逻辑只匹配关键词列表

### 最应该优先修的 3 件事

1. **修复 SearchOrchestrator 的检索逻辑**——接入真正可用的 TF-IDF/BM25 或稠密检索
2. **修复 AnswerValidator 的置信度逻辑错误**——这是导致"high confidence = high uncertainty"荒谬结果的直接原因
3. **重新设计 Planner 的 retrieval_targets 路由规则**——当前规则导致 character_card 被过度优先，而 event_timeline/chapter_chunks 被压制

---

## 1. 审计范围与方法

### 本次审计查看了哪些文件

| 文件路径 | 审计重点 |
|---------|---------|
| README.md | 宣称能力与实际实现对比 |
| requirements.txt | 依赖完整性与版本合理性 |
| fanren_eval_readme.md | 评测设计意图 |
| eval_runner_template.py | 评测逻辑实现 |
| fanren_eval_cases_v1.jsonl | 评测用例质量 |
| novel_system/planner.py | 任务判定、检索路由逻辑 |
| novel_system/retrieval.py | 检索层接口设计 |
| novel_system/service.py | 核心业务流程 |
| novel_system/validator.py | 验证层逻辑 |
| novel_system/semantic_scorer.py | 语义相似度计算 |
| novel_system/models.py | 数据模型定义 |
| novel_system/indexing.py | 索引构建逻辑 |
| novel_system/search/orchestrator.py | 搜索编排实现 |
| novel_system/search/profiles.py | 目标配置 |
| novel_system/entity_extractor.py | 实体抽取实现 |
| novel_system/llm.py | LLM 客户端封装 |
| novel_system/artifacts/targets.py | 产物构建器 |
| scripts/build_index.py | 索引构建脚本 |
| scripts/run_eval.py | 评测运行脚本 |
| tests/test_search_orchestrator.py | 测试覆盖范围 |

### 重点审查的模块

- **Planner**：任务类型判定、retrieval_targets 路由、retrieval_intent 设计
- **Retrieval**：SearchOrchestrator 实现、TF-IDF/BM25 使用、稠密检索接入
- **Validator**：EvidenceGate 阈值、AnswerValidator groundedness 计算、逻辑错误
- **Index Pipeline**：索引构建质量、中间产物可用性

### 判断"效果差"根因的方法

1. **代码路径追踪**：从 service.py 的 ask() 方法出发，追踪完整执行路径
2. **实现细节审查**：检查每个模块的核心算法实现，而非只看接口设计
3. **边界条件测试**：分析空结果、低分结果、fallback 场景的处理逻辑
4. **数据流分析**：检查各模块之间的数据传递是否真正影响最终输出

### 审查维度

- 架构设计：模块划分是否合理
- 检索质量：召回率、准确率、排序质量
- Planner 质量：任务判定准确性、路由合理性
- Validator 质量：门槛设置、评分逻辑、置信度计算
- Memory 质量：状态持久化、跨轮次影响
- Safety 质量：剧透防护、注入防护、版权控制
- Eval 质量：评测口径、评分公式、用例覆盖
- 工程化：依赖管理、日志追踪、测试覆盖

---

## 2. 项目整体架构梳理

### 文字版系统架构图

```
用户请求
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│                      service.py: ask()                           │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ 1. Planner.plan() → 判定 task_type, retrieval_targets   │   │
│  │ 2. QueryRewriter.rewrite() → 别名扩展、指代消解          │   │
│  │ 3. HybridRetriever.retrieve() → 多目标检索              │   │
│  │ 4. EvidenceGate.evaluate() → 证据门槛判断               │   │
│  │ 5. _execute_answer_skill() / _execute_continuation_skill│   │
│  │ 6. AnswerValidator.validate() → 答案质量评估            │   │
│  │ 7. SpoilerGuard.detect_spoiler() → 剧透防护             │   │
│  │ 8. 返回 AskResponse                                      │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│                    数据层 (indexing.py)                          │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ BookIndexRepository                                       │   │
│  │ ├── corpora: {                                            │   │
│  │ │     "chapter_chunks": [...],      # 文本切片            │   │
│  │ │     "chapter_summaries": [...],   # 章节摘要            │   │
│  │ │     "event_timeline": [...],      # 事件时间线          │   │
│  │ │     "character_card": [...],      # 人物卡              │   │
│  │ │     "relationship_graph": [...],  # 关系图              │   │
│  │ │     "world_rule": [...],          # 世界规则            │   │
│  │ │     "canon_memory": [...],        # 设定记忆            │   │
│  │ │     "recent_plot": [...],         # 近期剧情            │   │
│  │ │     "style_samples": [...],       # 风格样本            │   │
│  │ │ }                                                        │   │
│  │ ├── vectorizers: {target: TfidfVectorizer}               │   │
│  │ └── matrices: {target: sparse_matrix}                    │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### 各模块职责与位置

| 模块 | 文件位置 | 职责 | 是否决定效果核心 |
|------|---------|------|-----------------|
| Planner | planner.py | 判定任务类型、选择检索目标 | **是** |
| QueryRewriter | planner.py | 扩展别名、消解指代 | 是 |
| HybridRetriever | retrieval.py | 多目标检索入口 | **是** |
| SearchOrchestrator | search/orchestrator.py | 检索编排实现 | **是** |
| EvidenceGate | validator.py | 证据门槛判断 | 是 |
| AnswerValidator | validator.py | 答案质量评估 | 是 |
| ContinuationValidator | validator.py | 续写一致性检查 | 是 |
| SpoilerGuard | validator.py | 剧透防护 | 否 |
| SemanticScorer | semantic_scorer.py | 语义相似度计算 | 是 |
| MiniMaxClient | llm.py | LLM 调用 | **是** |
| EntityExtractor | entity_extractor.py | 实体抽取与矛盾检测 | 辅助 |

### retrieval_targets 各目标职责

| Target | 数据来源 | 实际用途 | 当前实现质量 |
|--------|---------|---------|-------------|
| chapter_chunks | 文本切片 | 基础事实检索 | 有数据，但检索逻辑简陋 |
| event_timeline | 章节前三句 | 因果链检索 | 数据质量低，无真正事件抽取 |
| character_card | 人名频率统计 | 人物信息检索 | 数据有，但检索逻辑有缺陷 |
| relationship_graph | 共现统计 | 关系查询 | 数据存在，但使用有限 |
| world_rule | 规则句抽取 | 世界观约束 | 数据存在，但未被有效使用 |
| canon_memory | 摘要+事件合并 | 设定记忆 | 数据有，但检索未差异化 |
| recent_plot | 章节末尾句 | 近期剧情 | 数据有，但质量一般 |
| style_samples | 长段落抽取 | 文风参考 | 数据有，但未真正影响生成 |

### 架构层面的初步判断

**当前架构更像什么：**

一个"概念验证原型"（Proof of Concept），展示了 RAG 系统应该有哪些组件，但每个组件都停留在最基础实现。

**离"成熟小说问答系统"还差什么：**

1. **真正的检索引擎**：当前 SearchOrchestrator 的检索是字符计数，不是真正的 TF-IDF/BM25/稠密检索
2. **智能的任务路由**：当前 Planner 是硬编码关键词匹配，无法理解语义意图
3. **有效的 Rerank 层**：检索结果没有重排序，无法提升精排质量
4. **完善的评测闭环**：有评测脚本但没有与系统改进形成闭环
5. **真正的事件抽取**：event_timeline 只是取前三句，不是真正的事件结构化

---

## 3. 仓库实现与 README 宣称的一致性审查

| README 声称能力 | 代码中对应实现 | 实现程度判断 | 存在问题 | 影响 |
|----------------|---------------|-------------|---------|------|
| 智能问答：基于章节内容进行语义检索 | HybridRetriever + SearchOrchestrator | **部分实现** | 检索逻辑是字符计数，非真正语义检索 | 问答准确率低 |
| 情节续写：基于原著风格和人物设定 | ContinuationValidator + _execute_continuation_skill | **部分实现** | 风格保持依赖 LLM，无显式约束 | 续写质量不稳定 |
| 人物卡片：自动提取人物信息 | _build_character_cards | **名义存在但效果可疑** | 只统计出现频率，无真正人物属性抽取 | 人物卡信息不完整 |
| 时间线：梳理情节发展 | _build_event_timeline | **名义存在但效果可疑** | 只取章节前三句，非真正事件结构化 | 时间线无因果链 |
| 关系图谱：可视化人物关系网络 | get_interactive_graph | **已实现** | 共现统计+向量相似度 | 效果尚可但与问答割裂 |
| 混合检索：结合 TF-IDF 语义搜索与规则匹配 | SearchOrchestrator | **未真正实现** | TF-IDF 矩阵构建了但未在检索中使用 | 检索质量低 |
| 查询重写：自动扩展别名、消解指代 | QueryRewriter | **已实现** | 规则化实现，效果尚可 | 不影响整体效果 |
| 范围限制：支持章节范围查询，防止剧透 | scope_filter + SpoilerGuard | **已实现** | 关键词匹配，有基础防护 | 有一定效果 |
| 验证层：证据门控、答案验证、剧透防护 | EvidenceGate + AnswerValidator | **形式存在但效果可疑** | 存在严重逻辑错误 | 可能导致错误拒答或错误置信度 |
| 评测系统：集成评测脚本与可视化 Dashboard | run_eval.py + eval_runner_template.py | **已实现** | 但评分公式过于简化 | 无法真实反映系统质量 |

### 宣传层面与实际的差距分析

**README 给人的印象**：一个功能完整、技术先进的小说问答系统，有 Planner/Retrieval/Validator 分层架构，支持多种检索目标和验证机制。

**实际代码状态**：

1. **架构分层确实存在**，但每个层的实现都停留在"骨架"级别
2. **TF-IDF 声称的"语义检索"**：实际是字符级 n-gram 统计，且在 SearchOrchestrator 中完全未被使用
3. **"验证层"**：有完整的数据模型，但 groundedness 计算只检查关键词覆盖，且存在逻辑错误
4. **"人物卡片"和"时间线"**：只是简单的文本截取和频率统计，不是真正的结构化抽取

**结论**：README 的描述更像是"设计意图"而非"实现完成度"，存在明显的过度宣传。

---

## 4. 根因分析：为什么测试结果差、效果差、回答不稳定

### 4.1 检索层是最大瓶颈

**已确认事实**：
- `search/orchestrator.py:95-113` 的 `_sparse_fallback` 方法实现：
  ```python
  def _sparse_fallback(self, query: str, docs: list[dict[str, Any]], target: str):
      text_field = TARGET_PROFILES[target]["text_field"]
      results = []
      for doc in docs:
          text = str(doc.get(text_field, ""))
          overlap = sum(1 for char in query if char and char in text)
          if overlap > 0:
              score = overlap / max(1, len(query))
  ```
  这是**字符级重叠计数**，不是 TF-IDF/BM25，也不是稠密检索。

**影响**：
- 查询"韩立为什么会去参加七玄门的内门弟子测试"无法召回正确答案
- 因为字符重叠逻辑对中文语义无理解能力
- 即使索引中有正确答案，也检索不到

### 4.2 Planner 路由错误

**已确认事实**：
- `planner.py:242-244` 的规则：
  ```python
  if any(keyword in query for keyword in ("人物", "谁", "关系", "韩立", "张铁", "墨大夫", "舞岩", "韩胖子", "三叔")):
      retrieval_targets = ["character_card", *retrieval_targets]
      retrieval_intent = "alias_resolution"
  ```
  只要有"韩立"二字就优先检索 character_card，而忽略 event_timeline。

**影响**：
- 问"韩立为什么会去参加测试"会优先检索人物卡，但人物卡里没有"原因"信息
- 真正需要的 event_timeline/chapter_chunks 被排在后面或压制

### 4.3 Validator 逻辑错误

**已确认事实**：
- `validator.py:728-731` 的代码：
  ```python
  if validation_result.confidence == "high":
      uncertainty = "high"
  elif validation_result.confidence == "medium" and uncertainty == "low":
      uncertainty = "medium"
  ```
  这是**逻辑反了**：high confidence 应该对应 low uncertainty。

**影响**：
- 当证据充分、答案质量高时，系统反而报告 high uncertainty
- 导致评测指标混乱，无法正确评估系统表现

### 4.4 TF-IDF 构建了但未使用

**已确认事实**：
- `indexing.py:588-601` 的 `_build_vector_payload` 方法确实构建了 TF-IDF 矩阵
- 但 `search/orchestrator.py` 完全没有使用这些矩阵

**合理推断**：
- 原设计可能是想用 TF-IDF，但后来改用了简单的字符计数
- 或者是多人协作时，索引构建和检索实现没有对齐

### 4.5 答案生成缺乏真正的 groundedness

**已确认事实**：
- `validator.py:320-341` 的 `_compute_groundedness` 方法：
  ```python
  answer_keywords = self._extract_keywords(answer)
  covered = 0
  for kw in answer_keywords:
      if kw in evidence_text:
          covered += 1
  return covered / len(answer_keywords)
  ```
  只检查答案关键词是否出现在证据中，不检查答案主张是否有证据支持。

**影响**：
- 即使答案是幻觉，只要用了正确的词汇，也会被认为"grounded"
- 无法真正防止幻觉

### 4.6 Fallback 过于粗糙

**已确认事实**：
- `service.py:1542-1550` 的 `_fallback_qa` 方法：
  ```python
  if not hits:
      return "当前范围内没有足够证据，我无法确认这个问题。"
  lead = hits[0]
  answer = f"根据第{lead.document.get('chapter', 0)}章..."
  ```
  直接返回第一个命中结果的前 120 字，没有判断是否真的回答了问题。

**影响**：
- 即使检索结果与问题无关，也会返回硬编码格式的答案
- 用户体验差

### 4.7 event_timeline 和 character_card 数据质量低

**已确认事实**：
- `indexing.py:375-406` 的 `_build_event_timeline`：只取章节前三句作为事件描述
- `indexing.py:408-452` 的 `_build_character_cards`：只统计人名出现频率

**影响**：
- event_timeline 没有真正的事件因果关系
- character_card 没有人物属性（性格、外貌、能力）

---

## 5. 证据链式问题清单

### 问题 1：SearchOrchestrator 检索逻辑是字符计数，非真正的语义检索

**问题描述**
SearchOrchestrator 的 `_sparse_fallback` 方法只实现字符级重叠计数，完全没有使用 TF-IDF/BM25 或稠密检索。

**代码/文件证据**
- 文件：`search/orchestrator.py`
- 函数：`_sparse_fallback` (行 95-113)
- 代码片段：
  ```python
  overlap = sum(1 for char in query if char and char in text)
  if overlap > 0:
      score = overlap / max(1, len(query))
  ```
- indexing.py 中构建了 TF-IDF 矩阵但从未被 SearchOrchestrator 使用

**已确认事实 / 合理推断**
- 已确认事实：检索逻辑确实只是字符计数
- 合理推断：原设计可能想用 TF-IDF，但实现时简化了

**为什么这会导致效果差**
字符计数对中文语义无理解能力。查询"韩立为什么参加测试"和文本"韩立参加测试的原因"可能有很高语义相关度，但字符重叠分数很低。

**影响范围**
- 所有 QA 类评测用例
- 所有需要检索 chapter_chunks 的场景

**严重程度**：S0 致命

**修复优先级**：P0

**改动成本**：中（需要接入 scikit-learn 的 TF-IDF 或外部 embedding）

**预期收益**：高

**修复建议**
修改 SearchOrchestrator.retrieve() 方法，使用 book_index.vectorizers 和 book_index.matrices 进行 TF-IDF 检索。

---

### 问题 2：AnswerValidator 置信度逻辑错误

**问题描述**
AnswerValidator 中 `validation_result.confidence == "high"` 时将 `uncertainty` 设为 `"high"`，这是明显的逻辑错误。

**代码/文件证据**
- 文件：`validator.py`
- 函数：`ask()` 中的验证结果处理 (行 728-731)
- 代码片段：
  ```python
  if validation_result.confidence == "high":
      uncertainty = "high"  # 错误：应该是 "low"
  ```

**已确认事实 / 合理推断**
- 已确认事实：这是明显的代码 bug

**为什么这会导致效果差**
当证据充分、答案质量高时，系统反而报告 high uncertainty，导致：
1. 评测指标混乱
2. 用户对系统信任度降低

**影响范围**
- 所有经过 AnswerValidator 的回答
- uncertainty 指标完全失真

**严重程度**：S0 致命

**修复优先级**：P0

**改动成本**：低（一行代码）

**预期收益**：中

**修复建议**
```python
if validation_result.confidence == "high":
    uncertainty = "low"
```

---

### 问题 3：Planner 的 character_card 过度优先

**问题描述**
只要有"韩立"、"张铁"等人名关键词，就优先检索 character_card，而忽略 event_timeline/chapter_chunks。

**代码/文件证据**
- 文件：`planner.py`
- 函数：`plan()` (行 242-244)
- 代码片段：
  ```python
  if any(keyword in query for keyword in ("人物", "谁", "关系", "韩立", "张铁", "墨大夫", ...)):
      retrieval_targets = ["character_card", *retrieval_targets]
  ```

**已确认事实 / 合理推断**
- 已确认事实：规则确实存在
- 合理推断：设计者想优先返回人物信息，但未区分"问人物"和"问人物相关事件"

**为什么这会导致效果差**
问"韩立为什么参加测试"时：
1. 系统优先检索 character_card
2. 但人物卡里只有"姓名、出现章节"，没有"原因"信息
3. 真正需要的 chapter_chunks 被排在后面

**影响范围**
- 所有包含人名的问答

**严重程度**：S1 高

**修复优先级**：P0

**改动成本**：中

**预期收益**：高

**修复建议**
区分"问人物信息"和"问人物相关事件"：
- "韩立是谁"、"韩立的性格" → character_card 优先
- "韩立为什么..."、"韩立怎么..." → event_timeline/chapter_chunks 优先

---

### 问题 4：EvidenceGate 阈值设置不合理

**问题描述**
EvidenceGate 的 `HIGH_RELEVANCE_THRESHOLD = 0.5` 过高，而 `_compute_relevance` 的归一化逻辑也有问题。

**代码/文件证据**
- 文件：`validator.py`
- 类：`EvidenceGate` (行 82-206)
- 代码片段：
  ```python
  HIGH_RELEVANCE_THRESHOLD = 0.5
  # ...
  return min(1.0, weighted_sum / total_weight / 0.5)  # 归一化
  ```
  当所有 hit.score 都是 0.3 时，归一化后变成 0.6，看起来"通过了"，但实际相关性很低。

**已确认事实 / 合理推断**
- 已确认事实：阈值和归一化逻辑确实存在
- 合理推断：设计者可能没有验证真实数据分布

**为什么这会导致效果差**
大量低质量检索结果被判定为"证据充分"，导致：
1. 错误的答案被输出
2. 或者正确的拒答被跳过

**影响范围**
- 所有需要 EvidenceGate 判断的场景

**严重程度**：S1 高

**修复优先级**：P1

**改动成本**：中

**预期收益**：中

**修复建议**
1. 根据实际检索分数分布调整阈值
2. 使用 SemanticScorer 的语义相似度替代简单归一化

---

### 问题 5：event_timeline 数据只是章节前三句

**问题描述**
`_build_event_timeline` 方法只取章节前三句作为事件描述，没有真正的因果关系抽取。

**代码/文件证据**
- 文件：`indexing.py`
- 函数：`_build_event_timeline` (行 375-406)
- 代码片段：
  ```python
  for sentence in sentences:
      compact = sentence.strip()
      if len(compact) < 12:
          continue
      picked.append(compact)
      if len(picked) >= 3:
          break
  description = " ".join(picked)[:260]
  ```

**已确认事实 / 合理推断**
- 已确认事实：实现确实只是取前三句
- 合理推断：这是为了快速完成索引构建，牺牲了质量

**为什么这会导致效果差**
章节前三句往往只是"场景描写"，而非"关键事件"：
- 第 5 章前三句可能是"韩立和张铁站在山脚下，看着眼前的炼骨崖..."
- 而真正的事件"两人都没按时到达崖顶，但因表现突出被留下做记名弟子"在后文

**影响范围**
- 所有需要因果链推理的问答
- planner retrieval intent = "causal_chain" 的场景

**严重程度**：S1 高

**修复优先级**：P1

**改动成本**：高（需要 NLP 或 LLM 辅助）

**预期收益**：中

**修复建议**
使用 LLM 提取每个章节的关键事件，构建真正的事件时间线。

---

### 问题 6：character_card 没有真正的属性抽取

**问题描述**
`_build_character_cards` 方法只统计人名出现频率，没有抽取性格、外貌、能力等属性。

**代码/文件证据**
- 文件：`indexing.py`
- 函数：`_build_character_cards` (行 408-452)
- 代码片段：
  ```python
  profile = f"姓名：{name}；首次出现章节：{chapters_list[0]}；相关章节：{chapters_list[:8]}。"
  if snippets:
      profile += f" 证据摘要：{snippets}"
  ```
  只有人名、章节和简单摘要，没有性格、外貌、能力。

**已确认事实 / 合理推断**
- 已确认事实：实现确实只有频率统计
- 合理推断：项目有 EntityExtractor 模块，但未用于索引构建

**为什么这会导致效果差**
问"韩立的性格是什么"时，character_card 无法提供有效信息。

**影响范围**
- 人物分析类问题
- 续写时的人物一致性检查

**严重程度**：S2 中

**修复优先级**：P2

**改动成本**：高

**预期收益**：中

**修复建议**
使用 EntityExtractor 或 LLM 抽取人物属性，存入 character_card。

---

### 问题 7：groundedness 计算只是关键词覆盖

**问题描述**
`_compute_groundedness` 方法只检查答案关键词是否出现在证据中，不检查答案主张是否有证据支持。

**代码/文件证据**
- 文件：`validator.py`
- 函数：`_compute_groundedness` (行 320-341)
- 代码片段：
  ```python
  answer_keywords = self._extract_keywords(answer)
  for kw in answer_keywords:
      if kw in evidence_text:
          covered += 1
  return covered / len(answer_keywords)
  ```

**已确认事实 / 合理推断**
- 已确认事实：实现确实只是关键词覆盖
- 合理推断：设计者可能知道这不是最佳方案，但选择了简化实现

**为什么这会导致效果差**
答案"韩立因为想变强所以参加测试"（错误原因）和证据"韩立参加测试是因为三叔推举"都包含"韩立"、"参加"、"测试"等关键词，groundedness 会很高。

**影响范围**
- 幻觉检测失效
- 答案质量评估失真

**严重程度**：S1 高

**修复优先级**：P1

**改动成本**：中

**预期收益**：中

**修复建议**
使用 NLI 模型或 LLM 验证答案主张是否有证据支持。

---

### 问题 8：续写 fallback 是硬编码模板

**问题描述**
`_fallback_continuation` 和 `_fallback_safe_continuation` 返回的是硬编码模板，没有实际续写能力。

**代码/文件证据**
- 文件：`service.py`
- 函数：`_fallback_continuation` (行 1584-1590)
- 文件：`novel_heuristics.py`
- 函数：`get_continuation_template`

**已确认事实 / 合理推断**
- 已确认事实：fallback 确实返回硬编码模板
- 合理推断：这是安全机制，但应该在有 LLM 时避免触发

**为什么这会导致效果差**
当 LLM 调用失败或被禁用时，续写质量极差。

**影响范围**
- 续写评测用例
- 无 LLM 环境下的用户体验

**严重程度**：S2 中

**修复优先级**：P2

**改动成本**：中

**预期收益**：低

**修复建议**
改进 fallback 逻辑，使用检索到的内容进行简单的句子拼接或模板填充。

---

### 问题 9：Memory 状态未真正影响检索

**问题描述**
MemoryState 被计算，但只用于渲染提示词，不真正影响检索策略或范围。

**代码/文件证据**
- 文件：`planner.py`
- 函数：`infer_memory` (行 139-154)
- 文件：`service.py`
- `_render_memory` 只用于生成提示词文本

**已确认事实 / 合理推断**
- 已确认事实：memory 只影响提示词
- 合理推断：设计者可能计划更深入集成，但未完成

**为什么这会导致效果差**
用户说"只看前 14 章"时，系统仍然可能检索到超出范围的证据，然后靠 SpoilerGuard 事后处理。

**影响范围**
- 跨轮次对话
- 用户偏好记忆

**严重程度**：S2 中

**修复优先级**：P2

**改动成本**：中

**预期收益**：中

**修复建议**
将 memory.no_spoiler 和 memory.scope_note 直接传递给检索层，缩小检索范围。

---

### 问题 10：评测评分公式过于简化

**问题描述**
`eval_runner_template.py` 的评分公式只计算 planner_score、required_score、forbidden_score 的加权平均，无法区分"答案错误但关键词覆盖"的情况。

**代码/文件证据**
- 文件：`eval_runner_template.py`
- 函数：`eval_case` (行 107-161)

**已确认事实 / 合理推断**
- 已确认事实：评分公式确实简化
- 合理推断：这是为了让评测可自动化运行

**为什么这会导致效果差**
评测分数可能虚高，无法真实反映系统质量。

**影响范围**
- 评测报告可信度
- 改进方向判断

**严重程度**：S2 中

**修复优先级**：P2

**改动成本**：中

**预期收益**：中

**修复建议**
引入 LLM-as-a-judge 进行答案质量评估。

---

### 问题 11：requirements.txt 缺少关键依赖

**问题描述**
requirements.txt 只有 9 个依赖，缺少 numpy、scikit-learn 等核心科学计算库的明确版本。

**代码/文件证据**
- 文件：`requirements.txt`
- 内容：
  ```
  fastapi>=0.135
  uvicorn>=0.44
  python-multipart>=0.0.26
  numpy>=2.3
  scikit-learn>=1.7
  pydantic>=2.12
  requests>=2.32
  jinja2>=3.1
  python-json-logger>=2.0.0
  ```
  缺少：
  - openai 或 minimax SDK（虽然代码中使用 requests 直接调用）
  - embedding 相关库（如果要用本地 embedding）

**已确认事实 / 合理推断**
- 已确认事实：依赖列表较短
- 合理推断：项目使用 requests 直接调用 API，未使用官方 SDK

**为什么这会导致效果差**
不同环境可能安装不同版本，导致行为不一致。

**影响范围**
- 环境复现
- CI/CD 稳定性

**严重程度**：S3 低

**修复优先级**：P3

**改动成本**：低

**预期收益**：低

**修复建议**
添加完整依赖列表，锁定版本。

---

### 问题 12：测试用例覆盖不足

**问题描述**
tests/ 目录下的测试主要是单元测试，测试单个函数的行为，没有端到端的效果测试。

**代码/文件证据**
- 文件：`tests/test_search_orchestrator.py`
- 测试内容：只测试了精确别名匹配、去重、数据类字段

**已确认事实 / 合理推断**
- 已确认事实：测试覆盖有限
- 合理推断：开发者可能认为功能正确性比效果更重要

**为什么这会导致效果差**
代码"能跑"但效果差，测试通过不代表系统真的好用。

**影响范围**
- 回归测试
- 代码重构风险

**严重程度**：S2 中

**修复优先级**：P2

**改动成本**：中

**预期收益**：中

**修复建议**
添加端到端测试，验证从用户输入到最终答案的完整流程。

---

### 问题 13：artifacts 模块存在但未在主流程中使用

**问题描述**
项目有 `novel_system/artifacts/` 目录，包含 SceneSegmentBuilder、CharacterRegistryBuilder 等模块，但 `indexing.py` 的主流程没有使用这些模块。

**代码/文件证据**
- 目录：`novel_system/artifacts/`
- 文件：`scene_segments.py`、`character_registry.py`、`targets.py`
- 文件：`indexing.py` 有独立的 `_build_*` 方法

**已确认事实 / 合理推断**
- 已确认事实：存在两套实现
- 合理推断：artifacts 模块可能是后来重构添加的，但主流程未迁移

**为什么这会导致效果差**
代码不一致，维护困难，新功能可能只在一个分支实现。

**影响范围**
- 代码可维护性
- 功能一致性

**严重程度**：S2 中

**修复优先级**：P2

**改动成本**：中

**预期收益**：中

**修复建议**
统一索引构建流程，使用 artifacts 模块替代 indexing.py 中的硬编码实现。

---

## 6. 分模块审计结论

### 6.1 Planner 审计结论

**当前实现情况**：
- RuleBasedPlanner 类实现了基于关键词的任务判定
- 支持 qa、summary、extract、analysis、continuation、copyright_request 六种任务类型
- retrieval_targets 通过硬编码规则确定
- 有 MemoryState 推断能力

**主要问题**：
1. 关键词匹配过于粗糙，无法区分"问人物"和"问人物相关事件"
2. character_card 被过度优先
3. retrieval_intent 字段存在但未在检索中真正使用
4. 无语义理解能力

**对整体效果的影响**：
- 检索目标选择错误，导致召回内容与问题不匹配
- 是"回答跑题"的重要原因之一

**修复方向**：
- 引入 LLM 做语义判断
- 或细化规则，区分不同查询模式

---

### 6.2 Retrieval 审计结论

**当前实现情况**：
- HybridRetriever 是入口层，委托给 SearchOrchestrator
- SearchOrchestrator 实现了多目标检索编排
- 但核心检索逻辑 `_sparse_fallback` 只是字符计数
- TF-IDF 矩阵在 indexing.py 中构建，但未在检索中使用

**主要问题**：
1. 没有真正的语义检索能力
2. 字符计数对中文效果差
3. 没有 rerank 层
4. TF-IDF 资源浪费

**对整体效果的影响**：
- **这是导致效果差的最核心原因**
- 即使有正确答案在索引中，也检索不到

**修复方向**：
- 接入真正的 TF-IDF/BM25
- 或使用 embedding 做稠密检索
- 添加 rerank 层

---

### 6.3 Search / Orchestrator 审计结论

**当前实现情况**：
- 支持多目标检索编排
- 有精确别名匹配能力
- 有章节范围过滤
- 有去重逻辑

**主要问题**：
1. `_sparse_fallback` 实现过于简陋
2. 没有 vectorizers/matrices 的使用
3. 评分逻辑不合理

**对整体效果的影响**：
- 召回率和准确率都低
- 排序质量差

**修复方向**：
- 使用 TF-IDF 矩阵进行检索
- 改进评分公式

---

### 6.4 Answer Synthesis 审计结论

**当前实现情况**：
- `_execute_answer_skill` 组装 prompt 调用 LLM
- 有 fallback 机制
- 有 scope 和 memory 提示

**主要问题**：
1. prompt 设计较简单
2. fallback 是硬编码格式
3. 没有答案格式约束

**对整体效果的影响**：
- 答案质量主要依赖 LLM 能力
- fallback 体验差

**修复方向**：
- 优化 prompt 设计
- 改进 fallback 逻辑

---

### 6.5 Validator 审计结论

**当前实现情况**：
- EvidenceGate 有阈值判断
- AnswerValidator 有 groundedness 计算
- ContinuationValidator 有一致性检查
- SpoilerGuard 有剧透检测

**主要问题**：
1. **置信度逻辑错误**（critical bug）
2. groundedness 只检查关键词覆盖
3. 阈值设置不合理
4. EntityExtractor 集成但效果有限

**对整体效果的影响**：
- uncertainty 指标失真
- 幻觉检测失效
- 可能错误拒答或错误放行

**修复方向**：
- 修复置信度逻辑 bug
- 改进 groundedness 计算
- 调整阈值

---

### 6.6 Memory 审计结论

**当前实现情况**：
- MemoryState 数据类存在
- infer_memory 能从历史推断偏好
- 但只影响提示词渲染

**主要问题**：
1. 不影响检索策略
2. 不影响范围控制
3. 跨轮次记忆有限

**对整体效果的影响**：
- 用户偏好记忆无效
- 跨轮次对话体验差

**修复方向**：
- 将 memory 传递给检索层
- 实现真正的范围控制

---

### 6.7 Safety / Governance 审计结论

**当前实现情况**：
- SpoilerGuard 有剧透检测
- 有 copyright_request 处理
- 有 prompt injection 隔离概念

**主要问题**：
1. 剧透检测只是关键词匹配
2. 注入防护依赖 LLM 自身能力
3. 无真正的版权控制

**对整体效果的影响**：
- 有一定防护能力，但不完善
- 安全性中等

**修复方向**：
- 加强剧透检测规则
- 添加更多安全检查

---

### 6.8 Evaluation 审计结论

**当前实现情况**：
- 有评测用例文件
- 有评测脚本
- 有 HTML 报告生成

**主要问题**：
1. 评分公式过于简化
2. 无法区分"关键词覆盖但答案错误"
3. 无端到端效果验证

**对整体效果的影响**：
- 评测分数可能虚高
- 无法指导改进

**修复方向**：
- 引入 LLM-as-a-judge
- 添加更多评测维度

---

### 6.9 Index / Data Pipeline 审计结论

**当前实现情况**：
- indexing.py 实现了完整的索引构建流程
- 有多种中间产物（chapter_chunks, event_timeline, character_card 等）
- 支持 pickle 缓存

**主要问题**：
1. event_timeline 只是取前三句
2. character_card 只是频率统计
3. artifacts 模块未集成
4. 无增量更新能力

**对整体效果的影响**：
- 检索目标数据质量低
- 限制了系统上限

**修复方向**：
- 使用 LLM 提升数据质量
- 集成 artifacts 模块

---

### 6.10 Service / API / Frontend Interface 审计结论

**当前实现情况**：
- FastAPI 应用完整
- 有 Swagger 文档
- 有前端界面

**主要问题**：
1. API 设计合理，但后端实现有限
2. 前端功能基础

**对整体效果的影响**：
- 用户体验基础
- 可展示性中等

**修复方向**：
- 提升后端质量

---

### 6.11 Tests / Observability / Engineering 审计结论

**当前实现情况**：
- 有 10 个测试文件
- 有 tracing 模块
- 有日志配置

**主要问题**：
1. 测试主要是单元测试
2. 无端到端效果测试
3. tracing 数据丰富但分析困难

**对整体效果的影响**：
- 代码质量有保障
- 但效果无保障

**修复方向**：
- 添加端到端测试
- 改进 tracing 分析工具

---

## 7. 优先级排序：先改什么最值

| 排名 | 问题 | 优先级 | 修改成本 | 预期收益 | 为什么先改 |
|------|------|--------|---------|---------|-----------|
| 1 | SearchOrchestrator 检索逻辑简陋 | P0 | 中 | 高 | 这是导致效果差的最核心原因，改后所有 QA 都会改善 |
| 2 | AnswerValidator 置信度逻辑错误 | P0 | 低 | 中 | 一行代码修复，立刻消除明显 bug |
| 3 | Planner character_card 过度优先 | P0 | 中 | 高 | 影响所有含人名的问答，改善检索路由 |
| 4 | EvidenceGate 阈值不合理 | P1 | 中 | 中 | 影响拒答决策，修复后评测指标更准确 |
| 5 | groundedness 计算简陋 | P1 | 中 | 中 | 影响幻觉检测，但对整体效果依赖检索质量 |
| 6 | event_timeline 数据质量低 | P1 | 高 | 中 | 数据层面改进，但需要更多工程量 |
| 7 | character_card 无属性抽取 | P2 | 高 | 中 | 数据层面改进，可后期优化 |
| 8 | Memory 不影响检索 | P2 | 中 | 中 | 影响跨轮次体验，但单轮问答更关键 |
| 9 | 评测评分公式简化 | P2 | 中 | 中 | 影响改进方向判断，但不影响系统效果 |
| 10 | artifacts 模块未集成 | P2 | 中 | 低 | 代码一致性问题，但功能已有替代实现 |

---

## 8. 分阶段改进路线图

### 第一阶段：1~3 天内最值得先做的修复

**目标**：修复致命 bug，建立可验证的改进基线

**要改哪些文件**：
1. `novel_system/search/orchestrator.py` - 接入 TF-IDF 检索
2. `novel_system/validator.py` - 修复置信度逻辑 bug
3. `novel_system/planner.py` - 调整 character_card 路由规则

**每项改动的具体内容**：

1. **SearchOrchestrator 接入 TF-IDF**：
   ```python
   def retrieve(self, book_index, query, targets, chapter_scope, top_k):
       hits = []
       for target in targets:
           vectorizer = book_index.vectorizers.get(target)
           matrix = book_index.matrices.get(target)
           docs = book_index.corpora.get(target, [])

           if vectorizer and matrix:
               query_vec = vectorizer.transform([query])
               scores = (matrix @ query_vec.T).toarray().ravel()
               # 取 top_k
               top_indices = scores.argsort()[-top_k:][::-1]
               for idx in top_indices:
                   if scores[idx] > 0:
                       hits.append(Hit(target=target, document=docs[idx], score=float(scores[idx])))
           else:
               # fallback to character overlap
               hits.extend(self._sparse_fallback(query, docs, target))
       return sorted(hits, key=lambda h: h.score, reverse=True)[:top_k]
   ```

2. **修复置信度逻辑**：
   ```python
   # 原来（错误）：
   if validation_result.confidence == "high":
       uncertainty = "high"

   # 修复后：
   if validation_result.confidence == "high":
       uncertainty = "low"
   ```

3. **调整 Planner 路由**：
   ```python
   # 原来：
   if any(keyword in query for keyword in ("韩立", "张铁", ...)):
       retrieval_targets = ["character_card", *retrieval_targets]

   # 改为：区分"问人物信息"和"问人物相关事件"
   if any(kw in query for kw in ("是谁", "人物卡", "性格", "外貌")):
       retrieval_targets = ["character_card", *retrieval_targets]
   elif any(kw in query for kw in ("为什么", "怎么", "原因", "结果")):
       retrieval_targets = ["event_timeline", "chapter_chunks"]
   ```

**为什么这一阶段先做这些**：
- P0 问题直接决定系统可用性
- 改动量小，风险可控
- 效果提升明显

**风险点**：
- TF-IDF 接入后需要调整阈值
- Planner 规则可能遗漏边界情况

**验收方法**：
- 运行 `fanren_eval_cases_v1.jsonl` 前 10 个 QA 用例
- 预期：qa_001 ~ qa_010 的分数明显提升

**建议优先复测哪些 case**：
- qa_001: 韩立参加七玄门测试的原因
- qa_003: 韩立与张铁的结果
- planner_001: 问答任务的检索决策

---

### 第二阶段：1~2 周内把效果明显拉起来的修复

**目标**：提升检索质量和验证效果

**要改哪些文件**：
1. `novel_system/validator.py` - 改进 groundedness 计算
2. `novel_system/indexing.py` - 使用 LLM 提升数据质量
3. `novel_system/service.py` - 改进 fallback 逻辑

**每项改动的具体内容**：

1. **改进 groundedness 计算**：
   - 使用 SemanticScorer 计算答案与证据的语义相似度
   - 或使用 NLI 模型验证答案主张

2. **使用 LLM 提升数据质量**：
   - event_timeline: 用 LLM 提取每个章节的 3-5 个关键事件
   - character_card: 用 LLM 抽取人物属性

3. **改进 fallback 逻辑**：
   - 使用检索到的 top-3 内容生成摘要式回答
   - 而非硬编码模板

**为什么这一阶段做这些**：
- 第一阶段修复了致命问题，第二阶段提升质量
- 需要更多工程量和测试

**验收方法**：
- 运行完整评测集
- 预期：overall_score 从基线提升 20%+

---

### 第三阶段：把项目提升到更接近当前优秀项目水准的增强项

**目标**：完善系统架构，提升可维护性和可扩展性

**要改哪些文件**：
1. 统一索引构建流程，集成 artifacts 模块
2. 添加 Rerank 层
3. 完善 Memory 机制
4. 改进评测体系

**每项改动的具体内容**：

1. **集成 artifacts 模块**：
   - 删除 indexing.py 中的硬编码实现
   - 使用 artifacts/ 下的 SceneSegmentBuilder、CharacterRegistryBuilder

2. **添加 Rerank 层**：
   - 检索后使用 cross-encoder 重排序
   - 或使用 LLM 做精排

3. **完善 Memory 机制**：
   - MemoryState 直接传递给检索层
   - 实现真正的范围控制和偏好记忆

4. **改进评测体系**：
   - 引入 LLM-as-a-judge
   - 添加更多评测维度

**为什么这一阶段做这些**：
- 前两阶段解决了核心效果问题
- 第三阶段提升工程质量和可维护性

---

## 9. 最小可行 Patch 清单

### Patch 1：修复 AnswerValidator 置信度逻辑 bug

- **文件**：`novel_system/validator.py`
- **当前问题**：`validation_result.confidence == "high"` 时将 `uncertainty` 设为 `"high"`
- **修改目标**：纠正逻辑，high confidence = low uncertainty
- **具体改法**：
  ```python
  # 行 728-731
  # 修改前：
  if validation_result.confidence == "high":
      uncertainty = "high"

  # 修改后：
  if validation_result.confidence == "low":
      uncertainty = "high"
  elif validation_result.confidence == "medium" and uncertainty == "low":
      uncertainty = "medium"
  ```
- **预期收益**：消除明显 bug，uncertainty 指标恢复正常
- **相关风险**：低，一行代码修改

---

### Patch 2：SearchOrchestrator 接入 TF-IDF 检索

- **文件**：`novel_system/search/orchestrator.py`
- **当前问题**：`_sparse_fallback` 只做字符计数，无语义检索能力
- **修改目标**：使用 book_index.vectorizers 和 book_index.matrices 进行 TF-IDF 检索
- **具体改法**：
  ```python
  def retrieve(self, book_index, query, targets, chapter_scope, top_k):
      hits = []
      for target in targets:
          docs = list(book_index.corpora.get(target, []))
          if chapter_scope:
              docs = [doc for doc in docs if self._in_scope(doc, chapter_scope)]

          # 尝试使用 TF-IDF
          vectorizer = book_index.vectorizers.get(target)
          matrix = book_index.matrices.get(target)

          if vectorizer is not None and matrix is not None:
              query_vec = vectorizer.transform([query])
              scores = (matrix @ query_vec.T).toarray().ravel()
              top_indices = scores.argsort()[-top_k:][::-1]
              for idx in top_indices:
                  if scores[idx] > 0 and idx < len(docs):
                      hits.append({
                          "target": target,
                          "document_id": docs[idx].get("id", f"doc-{idx}"),
                          "document": docs[idx],
                          "score": float(scores[idx]),
                      })
          else:
              # fallback to character overlap
              hits.extend(self._sparse_fallback(query, docs, target))

      deduped = self._dedupe_candidates(hits)
      deduped.sort(key=lambda item: item["score"], reverse=True)
      return [Hit(target=item["target"], document=item["document"], score=item["score"])
              for item in deduped[:top_k]]
  ```
- **预期收益**：检索质量大幅提升，QA 准确率提高
- **相关风险**：中，需要测试阈值调整

---

### Patch 3：调整 Planner 的 character_card 路由规则

- **文件**：`novel_system/planner.py`
- **当前问题**：只要有"韩立"等关键词就优先检索 character_card
- **修改目标**：区分"问人物信息"和"问人物相关事件"
- **具体改法**：
  ```python
  # 行 242-244，修改为：
  # 问人物信息 → character_card 优先
  if any(keyword in query for keyword in ("是谁", "人物卡", "性格", "外貌", "什么人")):
      retrieval_targets = ["character_card", *retrieval_targets]
      retrieval_intent = "alias_resolution"
  # 问人物相关事件 → event_timeline/chapter_chunks 优先
  elif any(keyword in query for keyword in ("为什么", "怎么", "原因", "结果", "发生了什么")):
      retrieval_targets = ["event_timeline", "chapter_chunks"]
      retrieval_intent = "causal_chain"
  # 默认：只含人名，不特殊处理
  ```
- **预期收益**：减少检索路由错误
- **相关风险**：低，规则调整

---

### Patch 4：调整 EvidenceGate 阈值

- **文件**：`novel_system/validator.py`
- **当前问题**：`HIGH_RELEVANCE_THRESHOLD = 0.5` 过高，归一化逻辑有问题
- **修改目标**：根据实际数据分布调整阈值
- **具体改法**：
  ```python
  # 行 92-94，修改为：
  HIGH_RELEVANCE_THRESHOLD = 0.3
  MEDIUM_RELEVANCE_THRESHOLD = 0.15
  MIN_HITS_FOR_CONFIDENCE = 2

  # 行 176-205，修改 _compute_relevance：
  def _compute_relevance(self, query: str, hits: list[Any]) -> float:
      if not hits:
          return 0.0
      scores = []
      for hit in hits:
          if hasattr(hit, 'score'):
              raw_score = hit.score
          elif isinstance(hit, dict):
              raw_score = hit.get('score', 0.0)
          else:
              raw_score = 0.0
          # TF-IDF 分数归一化：假设高分在 0.3-0.6 范围
          normalized = min(1.0, raw_score / 0.4)
          scores.append(normalized)

      # 指数衰减加权平均
      weights = [0.5 ** i for i in range(len(scores))]
      return sum(s * w for s, w in zip(scores, weights)) / sum(weights)
  ```
- **预期收益**：拒答决策更合理
- **相关风险**：中，需要根据实际数据微调

---

### Patch 5：改进 groundedness 计算

- **文件**：`novel_system/validator.py`
- **当前问题**：只检查关键词覆盖，不检查答案主张是否有证据支持
- **修改目标**：使用 SemanticScorer 计算语义相似度
- **具体改法**：
  ```python
  def _compute_groundedness(self, answer: str, evidence: list[EvidenceItem]) -> float:
      if not evidence:
          return 0.0

      evidence_text = " ".join(e.quote for e in evidence if e.quote)

      # 如果有 SemanticScorer，使用语义相似度
      if self.semantic_scorer:
          try:
              score, _ = self.semantic_scorer.compute_similarity_with_hits(
                  answer, [type('Hit', (), {'document': {'text': evidence_text}, 'score': 1.0})()]
              )
              return score
          except Exception:
              pass

      # fallback to keyword coverage
      answer_keywords = self._extract_keywords(answer)
      if not answer_keywords:
          return 0.5
      covered = sum(1 for kw in answer_keywords if kw in evidence_text)
      return covered / len(answer_keywords)
  ```
- **预期收益**：幻觉检测更准确
- **相关风险**：中，依赖 SemanticScorer 可用性

---

### Patch 6：使用 LLM 提升 event_timeline 数据质量

- **文件**：`novel_system/indexing.py`
- **当前问题**：`_build_event_timeline` 只取章节前三句
- **修改目标**：使用 LLM 提取关键事件
- **具体改法**：
  ```python
  def _build_event_timeline_with_llm(self, chapters, llm_client):
      events = []
      for chapter in chapters:
          prompt = f"""
          请从以下章节内容中提取 3-5 个关键事件，每个事件用一句话描述：

          第{chapter['chapter']}章 {chapter['title']}
          {chapter['text'][:2000]}

          输出格式：每行一个事件，格式为"事件描述"
          """
          try:
              response = llm_client.chat([{"role": "user", "content": prompt}], temperature=0.3)
              event_texts = response.strip().split('\n')
              for i, event_text in enumerate(event_texts[:5]):
                  if event_text.strip():
                      events.append({
                          "id": f"event-{chapter['chapter']}-{i}",
                          "chapter": chapter["chapter"],
                          "title": chapter["title"],
                          "target": "event_timeline",
                          "text": event_text.strip(),
                          "description": event_text.strip(),
                          "participants": self._extract_person_names(event_text),
                          "source": f"第{chapter['chapter']}章 {chapter['title']}",
                      })
          except Exception:
              # fallback to original method
              events.extend(self._build_event_timeline([chapter], []))
      return events
  ```
- **预期收益**：因果链检索质量提升
- **相关风险**：高，需要 LLM API 调用成本

---

### Patch 7：改进 fallback 逻辑

- **文件**：`novel_system/service.py`
- **当前问题**：`_fallback_qa` 返回硬编码格式
- **修改目标**：使用检索内容生成更自然的回答
- **具体改法**：
  ```python
  def _fallback_qa(self, query: str, hits: list[RetrievalHit], scope: Scope, memory: MemoryState) -> str:
      if not hits:
          return "当前范围内没有足够证据，我无法确认这个问题。"

      # 收集所有命中的关键句子
      sentences = []
      for hit in hits[:3]:
          text = hit.document.get("text", "")
          # 提取与问题相关的句子
          for sentence in text.split("。"):
              if sentence.strip() and len(sentence.strip()) > 10:
                  sentences.append(sentence.strip())

      if not sentences:
          return f"根据第{hits[0].document.get('chapter', 0)}章，相关信息有限，无法完整回答。"

      # 组合前 3 个相关句子
      combined = "。".join(sentences[:3])
      chapter = hits[0].document.get("chapter", 0)
      return f"根据第{chapter}章，{combined}。"
  ```
- **预期收益**：fallback 体验改善
- **相关风险**：低

---

### Patch 8：添加检索结果日志

- **文件**：`novel_system/service.py`
- **当前问题**：检索结果只通过 trace 返回，不方便调试
- **修改目标**：添加结构化日志，便于分析检索质量
- **具体改法**：
  ```python
  import logging
  logger = logging.getLogger(__name__)

  # 在 _retrieve_with_rewrite 方法后添加：
  def _retrieve_with_rewrite(self, book_index, rewritten, planner, scope, top_k, simulate):
      hits = ... # existing retrieval logic

      # 添加日志
      logger.info(f"Retrieval result for query '{rewritten.original}':")
      for i, hit in enumerate(hits[:5]):
          logger.info(f"  [{i+1}] target={hit.target} score={hit.score:.4f} "
                     f"chapter={hit.document.get('chapter')} "
                     f"text_preview={hit.document.get('text', '')[:50]}...")

      return hits
  ```
- **预期收益**：便于调试和优化
- **相关风险**：低

---

### Patch 9：添加端到端测试

- **文件**：新建 `tests/test_e2e_qa.py`
- **当前问题**：无端到端效果测试
- **修改目标**：验证从输入到输出的完整流程
- **具体改法**：
  ```python
  def test_qa_001_korean_li_test_reason():
      """测试：韩立参加七玄门测试的原因"""
      from novel_system.service import create_service
      from novel_system.models import AskRequest, Scope

      service = create_service()
      service.index_default_book()

      response = service.ask(
          service.config.default_book_id,
          AskRequest(
              user_query="韩立为什么会去参加七玄门的内门弟子测试？",
              scope=Scope(chapters=[1]),
          )
      )

      # 验证答案包含关键信息
      assert "三叔" in response.answer or "韩胖子" in response.answer
      assert "推举" in response.answer or "参加" in response.answer
      assert response.uncertainty in ["low", "medium"]
      assert len(response.evidence) > 0
  ```
- **预期收益**：建立效果验证机制
- **相关风险**：低

---

### Patch 10：统一使用 artifacts 模块

- **文件**：`novel_system/indexing.py`
- **当前问题**：存在两套索引构建实现
- **修改目标**：使用 artifacts 模块替代硬编码实现
- **具体改法**：
  ```python
  from .artifacts.scene_segments import SceneSegmentBuilder
  from .artifacts.character_registry import CharacterRegistryBuilder
  from .artifacts.targets import build_chapter_chunks, build_event_timeline, build_character_cards

  def build_from_txt(self, book_id: str, title: str, source_path: Path):
      raw_text = source_path.read_text(encoding="utf-8")
      chapters = self._parse_chapters(raw_text)

      # 使用 artifacts 模块
      scene_builder = SceneSegmentBuilder()
      scenes = scene_builder.build(chapters)

      registry_builder = CharacterRegistryBuilder()
      registry = registry_builder.build(scenes)

      chapter_chunks = build_chapter_chunks(scenes)
      event_timeline = build_event_timeline(scenes)
      character_cards = build_character_cards(registry, scenes, event_timeline)

      # ... 其余逻辑
  ```
- **预期收益**：代码一致性和可维护性提升
- **相关风险**：中，需要验证产物兼容性

---

### Patch 11：添加 Rerank 层

- **文件**：新建 `novel_system/reranker.py`
- **当前问题**：无重排序机制
- **修改目标**：对检索结果进行精排
- **具体改法**：
  ```python
  class Reranker:
      def __init__(self, llm_client):
          self.llm = llm_client

      def rerank(self, query: str, hits: list, top_k: int = 5) -> list:
          if not hits or len(hits) <= top_k:
              return hits

          # 构建打分 prompt
          docs_text = "\n".join([
              f"[{i}] {h.document.get('text', '')[:200]}"
              for i, h in enumerate(hits)
          ])

          prompt = f"""请为以下文档与查询的相关性打分（0-10分）：

          查询：{query}

          文档：
          {docs_text}

          输出格式：每行一个分数，如 "5 7 3 8 6"
          """

          try:
              response = self.llm.chat([{"role": "user", "content": prompt}], temperature=0.1)
              scores = [float(s) for s in response.strip().split()]
              sorted_hits = [h for _, h in sorted(zip(scores, hits), key=lambda x: -x[0])]
              return sorted_hits[:top_k]
          except Exception:
              return hits[:top_k]
  ```
- **预期收益**：检索精排质量提升
- **相关风险**：中，依赖 LLM

---

### Patch 12：改进评测评分公式

- **文件**：`eval_runner_template.py`
- **当前问题**：评分公式过于简化
- **修改目标**：引入语义相似度评分
- **具体改法**：
  ```python
  def eval_case_with_semantic(case, pred, semantic_scorer=None):
      # ... existing logic ...

      # 新增：语义相似度评分
      semantic_score = 0.5
      if semantic_scorer and "answer" in pred:
          answer = pred["answer"]
          gold = case.get("expected_result", {}).get("gold_answer_short", "")
          if gold:
              try:
                  score, _ = semantic_scorer.compute_similarity_with_hits(
                      gold, [type('Hit', (), {'document': {'text': answer}, 'score': 1.0})()]
                  )
                  semantic_score = score
              except Exception:
                  pass

      # 调整总分公式
      total = 0.2 * pscore + 0.4 * rscore + 0.2 * fscore + 0.2 * semantic_score

      return {
          "id": case["id"],
          "score": round(total, 4),
          # ... other fields ...
          "semantic_score": round(semantic_score, 4),
      }
  ```
- **预期收益**：评测更准确反映效果
- **相关风险**：中

---

## 10. 测试与验收方案

### 每一阶段改完后该怎么复测

**第一阶段完成后**：
1. 运行 `python scripts/run_eval.py --cases fanren_eval_cases_v1.jsonl`
2. 重点关注 qa_001 ~ qa_010 的分数变化
3. 检查 uncertainty 指标是否恢复正常

**第二阶段完成后**：
1. 运行完整评测集
2. 对比 overall_score 和 pass_rate 变化
3. 分析失败案例的变化

**第三阶段完成后**：
1. 运行完整评测集
2. 对比架构改进前后的差异
3. 检查新增测试用例的覆盖情况

### 哪些 case 应该优先看

| Case ID | 类型 | 为什么优先 |
|---------|------|-----------|
| qa_001 | QA Grounded | 典型事实问答，测试检索效果 |
| qa_003 | QA Grounded | 跨人物问答，测试 character_card 路由 |
| planner_001 | Planner Retrieval | 测试检索决策正确性 |
| planner_002 | Planner Retrieval | 续写任务检索决策 |
| cont_001 | Continuation | 续写约束测试 |
| memory_002 | Memory Scope | 范围控制测试 |
| safety_001 | Prompt Injection | 注入防护测试 |
| safety_002 | Copyright Guard | 版权控制测试 |

### 应该新增哪些评测 case

1. **检索边界测试**：
   - 同义词查询（"二愣子" vs "韩立"）
   - 长查询（多条件组合）
   - 无关查询（应该拒答）

2. **多轮对话测试**：
   - 上下文依赖查询
   - 偏好记忆测试

3. **边界条件测试**：
   - 空查询
   - 超长查询
   - 特殊字符

### 应该记录哪些日志与指标

| 指标 | 来源 | 用途 |
|------|------|------|
| 检索召回数 | RetrievalTrace | 评估检索覆盖 |
| 检索分数分布 | RetrievalHitTrace | 评估检索质量 |
| EvidenceGate 判断结果 | EvidenceGateResult | 评估拒答决策 |
| AnswerValidator 分数 | AnswerValidationResult | 评估答案质量 |
| LLM token 使用量 | LLMResponse.usage | 成本监控 |
| 端到端延迟 | total_duration_ms | 性能监控 |

### 如何区分"检索问题""路由问题""生成问题""validator 问题"

1. **检索问题**：
   - 检查 RetrievalTrace.hits_count 是否为 0
   - 检查 top-1 hit 的 score 是否过低（< 0.1）
   - 检查 top-1 hit 的 document.chapter 是否在范围内

2. **路由问题**：
   - 检查 PlannerOutput.task_type 是否正确
   - 检查 retrieval_targets 是否包含正确目标
   - 检查是否遗漏了关键目标（如 event_timeline）

3. **生成问题**：
   - 检查 AnswerValidator.groundedness_score 是否高
   - 检查答案是否包含幻觉内容
   - 检查 LLM temperature 设置

4. **Validator 问题**：
   - 检查 EvidenceGateResult.sufficient 是否合理
   - 检查 uncertainty 是否与实际情况一致
   - 检查是否有误判

### 如何建立最基础的回归测试机制

1. **创建基准评测结果**：
   ```bash
   python scripts/run_eval.py --cases fanren_eval_cases_v1.jsonl --output-dir data/eval_baseline
   ```

2. **每次修改后运行对比**：
   ```bash
   python scripts/run_eval.py --cases fanren_eval_cases_v1.jsonl --output-dir data/eval_current
   python scripts/compare_eval.py --baseline data/eval_baseline --current data/eval_current
   ```

3. **设置 CI 门禁**：
   - overall_score 不能低于基线
   - P0 用例必须通过
   - 新增测试用例必须通过

---

## 11. 这个项目目前的真实定位与上限判断

### 1. 这个项目现在更像什么？

**判断：这是一个"功能骨架完整但效果链路未打通的 MVP 原型"**

它更像是：
- ✅ **概念验证原型**：展示了 RAG 系统应该有哪些组件
- ✅ **教学演示项目**：可以作为学习 RAG 架构的案例
- ❌ **成熟可用系统**：核心检索和验证逻辑存在严重缺陷
- ❌ **可直接展示项目**：效果不稳定，无法保证演示成功

### 2. 它当前最像"拼模块"，还是"真正打通效果链路"？

**判断：更接近"拼模块"**

证据：
1. artifacts 模块存在但未在主流程使用
2. TF-IDF 矩阵构建了但未在检索使用
3. Memory 状态计算了但未影响检索
4. 各模块独立存在，但缺乏有效联动

### 3. 它有哪些点可以写进简历，哪些点现在还不适合夸大？

**可以写的点**：
- ✅ 设计了 Planner / Retrieval / Validator 分层架构
- ✅ 实现了多目标检索编排
- ✅ 集成了 EvidenceGate 和 AnswerValidator 验证层
- ✅ 实现了剧透防护和版权控制概念
- ✅ 有结构化评测框架

**不建议夸大的点**：
- ❌ "语义检索能力"——实际是字符计数
- ❌ "智能问答系统"——效果不稳定
- ❌ "人物图谱生成"——只有共现统计
- ❌ "事件时间线"——只是章节前三句

### 4. 如果按正确方向继续改，最有希望先做出什么亮点？

**最有希望的改进方向**：
1. **修复检索层**后，QA 准确率会有明显提升，可以作为"可展示"的亮点
2. **使用 LLM 提升数据质量**后，event_timeline 会更真实，因果链推理会有改善
3. **完善评测体系**后，可以展示"有数据支撑的改进过程"

---

## 12. 总结结论

### 1. 这个仓库当前最本质的问题是什么？

**最本质的问题是：检索层极其简陋，导致整个系统"形似而神不似"。**

具体表现：
- SearchOrchestrator 的 `_sparse_fallback` 只是字符计数
- TF-IDF 矩阵构建了但从未使用
- 没有 BM25、没有稠密检索、没有 rerank

这个问题是"效果差"的根因，其他问题（Planner 路由、Validator 逻辑、数据质量）都是叠加因素。

### 2. 为什么它会出现"看起来功能不少，但测试和效果仍很差"？

**原因：每个模块都停留在"框架级实现"，缺乏真正决定效果的细节打磨。**

- Planner 有关键词匹配框架，但没有语义理解能力
- Retrieval 有接口抽象，但核心检索逻辑是字符计数
- Validator 有数据模型，但 groundedness 计算只是简单关键词覆盖
- Memory 有状态类，但不影响检索决策
- Safety 有剧透防护概念，但检测逻辑只匹配关键词

**本质是"设计意图"与"实现完成度"的巨大差距。**

### 3. 真正应该先救哪一层？

**最应该先救的是检索层。**

理由：
1. 检索是 RAG 系统的核心，决定了召回内容的质量
2. 当前检索实现是字符计数，几乎是"没有检索"
3. 修复检索层后，所有下游模块的效果都会改善
4. 修改成本中等（可以接入已构建的 TF-IDF），预期收益高

### 4. 给作者一句最尖锐但最有价值的建议是什么？

**"这个项目的模块框架已经搭好，但每个模块的核心算法都是简化实现。在继续添加新功能之前，请先花 3-5 天把检索层从'字符计数'升级到'真正的 TF-IDF 或稠密检索'——这是决定项目能否从'原型'变成'可用系统'的关键一步。"**

---

## 附录 A：关键文件与职责速查表

| 文件 | 职责 | 是否关键 | 是否需要优先修改 | 备注 |
|------|------|---------|-----------------|------|
| novel_system/service.py | 核心业务流程 | ✅ 是 | 否 | 入口文件，调用各模块 |
| novel_system/planner.py | 任务判定、检索路由 | ✅ 是 | ✅ 是 | P0 问题 |
| novel_system/search/orchestrator.py | 检索编排 | ✅ 是 | ✅ 是 | P0 问题 |
| novel_system/retrieval.py | 检索入口 | 是 | 否 | 委托给 SearchOrchestrator |
| novel_system/validator.py | 验证层 | ✅ 是 | ✅ 是 | P0 bug |
| novel_system/semantic_scorer.py | 语义相似度 | 是 | 否 | 依赖 embedding |
| novel_system/indexing.py | 索引构建 | ✅ 是 | ✅ 是 | P1 数据质量 |
| novel_system/llm.py | LLM 调用 | 是 | 否 | 基础可用 |
| novel_system/entity_extractor.py | 实体抽取 | 是 | 否 | 已有完整实现 |
| novel_system/artifacts/*.py | 产物构建 | 是 | 否 | 未集成到主流程 |
| scripts/run_eval.py | 评测运行 | 是 | 否 | 已有完整实现 |
| eval_runner_template.py | 评测逻辑 | 是 | ✅ 是 | P2 评分公式 |

---

## 附录 B：审计中发现的高风险误区

### 误区 1：认为"有 TF-IDF 矩阵就有语义检索"

事实：索引构建时确实创建了 TF-IDF 矩阵，但检索时完全未使用。不要被变量名迷惑。

### 误区 2：认为"测试通过意味着功能正确"

事实：测试主要是单元测试，测试的是"函数行为正确"而非"端到端效果好"。

### 误区 3：认为"模块多是好事"

事实：模块多但联动差，反而增加了维护成本。应该先打通核心链路。

### 误区 4：认为"换个更强的 LLM 就能解决问题"

事实：检索层是瓶颈，LLM 再强也无法从错误的检索结果中生成正确答案。

### 误区 5：认为"评测分数高意味着系统好用"

事实：评测评分公式过于简化，分数可能虚高。

---

## 附录 C：后续可扩展优化项

### 长期优化项（非 P0/P1）

1. **添加 Rerank 层**：使用 cross-encoder 或 LLM 对检索结果重排序
2. **实现增量索引**：支持新书添加和现有书更新
3. **添加多模态支持**：图片输入解析
4. **优化前端体验**：WebSocket 实时响应
5. **添加用户反馈机制**：收集用户评分，持续改进
6. **实现真正的 Memory 系统**：持久化用户偏好
7. **添加 LLM-as-a-judge 评测**：更准确的答案质量评估
8. **实现 A/B 测试框架**：验证改进效果
9. **添加监控告警**：检索质量、LLM 错误率监控
10. **优化成本**：缓存、批处理、模型选择

---

*报告结束*
