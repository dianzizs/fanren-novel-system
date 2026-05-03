# PRD: 图谱人物命名策略迁移与可配置化

## 1. Introduction / Overview

当前图谱构建流程含有与特定小说（如韩立）强耦合的硬编码规则，导致跨书迁移成本高、规则分叉风险高。该需求旨在将人物命名与别名规则从代码迁移到书籍级配置，并统一 `service.py` 与 `graph_service.py` 的重复规则，实现“默认启发式 + 书籍配置覆盖”的可迁移架构。

本期采用一次性切换策略（不保留旧实现分支），并同时达成：迁移能力与现有能力不退化。

## 2. Goals

- 将 `GRAPH_CANON_SEEDS` / `GRAPH_ALIAS_LOOKUP` 从代码迁移至书籍配置。
- 引入统一命名策略模块（`novel_system/graph_name_policy.py` 或 `name_normalizer.py`）消除 `service.py` 与 `graph_service.py` 规则重复。
- 建立“索引阶段人物候选抽取 -> 候选过滤 -> 角色注册表”标准链路。
- 约束 graph 消费面仅依赖：`character_registry`、`character_card`、`event_timeline`。
- 支持白名单机制，并可自动判定新书是否命中白名单策略。
- 保证迁移后现有核心链路无功能回退，且测试可验证。

## 3. User Stories

### US-001: 抽离统一人物命名策略模块
**Description:** As a backend developer, I want a single graph name policy module so that all graph-related naming/alias rules come from one place and never diverge.

**Acceptance Criteria:**
- [ ] 新增统一模块：`novel_system/graph_name_policy.py`（或等价命名模块）。
- [ ] `service.py` 与 `graph_service.py` 不再各自维护重复的人名规范化/过滤逻辑。
- [ ] 对外暴露清晰接口（如：规范化、别名归并、候选过滤入口）。
- [ ] 现有相关测试通过。

### US-002: 书籍级 graph 配置外置
**Description:** As a data/operator, I want per-book graph profile files so that novel-specific knowledge is managed as data instead of hardcoded patches.

**Acceptance Criteria:**
- [ ] 支持读取 `books/{book_id}/graph_profile.json`。
- [ ] `GRAPH_CANON_SEEDS` / `GRAPH_ALIAS_LOOKUP` 从代码常量迁出到配置层。
- [ ] 配置缺失时可回落到默认启发式，不因缺文件导致流程中断。
- [ ] 配置 schema 明确支持：人物种子、别名、少量人工修正字段。

### US-003: 索引阶段人物候选与过滤链路
**Description:** As a retrieval/graph engineer, I want candidate extraction and filtering in indexing so that fake names are filtered before graph consumption.

**Acceptance Criteria:**
- [ ] 索引阶段产出人物候选集合。
- [ ] 候选过滤至少包含三类证据：出现频率、章节跨度、场景证据。
- [ ] 过滤后生成 `character_registry`，并产出 canonical name + aliases。
- [ ] 对同一输入数据，过滤结果具有可重复性（同配置下稳定输出）。

### US-004: Graph 消费面收敛到标准产物
**Description:** As a graph pipeline maintainer, I want graph only consume normalized artifacts so that upstream changes do not repeatedly break graph rules.

**Acceptance Criteria:**
- [ ] graph 构建仅消费 `character_registry`、`character_card`、`event_timeline`。
- [ ] graph 侧不再直接依赖原始名字补丁常量。
- [ ] 非法输入（缺关键产物）有明确失败信号或日志。
- [ ] 现有图谱相关关键测试通过。

### US-005: 白名单与新书自动判定
**Description:** As an operator, I want a whitelist policy with auto-detection for new books so that migration strategy is controllable and scalable.

**Acceptance Criteria:**
- [ ] 新增可配置白名单机制（用于特定策略启用/约束）。
- [ ] 系统可自动判定新书是否在白名单中，并按判定结果执行对应策略。
- [ ] 白名单判定逻辑可测试（包含命中与未命中样例）。
- [ ] 判定结果在日志或调试输出中可追踪。

### US-006: 一次性切换与回归验证
**Description:** As a project owner, I want one-shot migration with strict verification so that architecture is cleaned up without long-term dual maintenance.

**Acceptance Criteria:**
- [ ] 本期不保留旧实现双轨逻辑（一次性切换）。
- [ ] 新增迁移相关测试覆盖关键路径。
- [ ] 现有测试 + 新增测试均通过。
- [ ] 至少在一个样书上验证人物图谱效果达预期（含 aliases 归并与假名过滤结果）。

## 4. Functional Requirements

- FR-1: 系统必须提供统一的人物命名策略模块，承载规范化、别名映射、候选过滤等逻辑。
- FR-2: 系统必须支持书籍级配置文件 `books/{book_id}/graph_profile.json`，用于小说专属人物知识与人工修正。
- FR-3: 系统必须将代码内 `GRAPH_CANON_SEEDS` / `GRAPH_ALIAS_LOOKUP` 迁移为配置驱动。
- FR-4: 索引阶段必须先抽取人物候选，再基于出现频率、章节跨度、场景证据进行过滤。
- FR-5: 系统必须生成并维护 `character_registry`，其中每个角色包含 canonical name 与 aliases。
- FR-6: graph 构建流程必须仅消费 `character_registry`、`character_card`、`event_timeline` 三类标准产物。
- FR-7: 每本书最多允许一个可选 `graph_profile.json`，仅用于少量人工修正，不承载完整业务流程逻辑。
- FR-8: 系统必须提供白名单配置，并自动判定新书是否在白名单中。
- FR-9: 白名单命中结果必须可观测（日志/trace/debug 输出）。
- FR-10: 本期迁移采用一次性切换，不引入长期新旧规则并行分支。

## 5. Non-Goals (Out of Scope)

- 不在本期引入多份 profile 合并策略（每书仅单一 profile）。
- 不在本期建设可视化配置管理后台。
- 不在本期覆盖全部小说的高质量人工标注，只提供可迁移机制与少量人工修正入口。
- 不在本期重写与 graph 无关的 retrieval/reranker 全链路。
- 不在本期做跨项目通用 SDK 抽象。

## 6. Design Considerations

- 配置优先级建议：书籍 profile > 默认启发式。
- 默认启发式应保持通用，不再内嵌“单书专属补丁”。
- 白名单规则应简洁透明，避免隐式分支导致排查困难。

## 7. Technical Considerations

- 新模块建议位置：`novel_system/graph_name_policy.py`。
- 新配置建议位置：`books/{book_id}/graph_profile.json`。
- 需要统一 `service.py` 与 `graph_service.py` 的调用入口，避免重复实现。
- 建议定义 `graph_profile.json` 的 schema 与默认值行为，确保缺省配置可安全运行。
- 需要补充单元测试与集成测试：
  - 配置加载与回退
  - 别名归并与 canonical 决议
  - 候选过滤三证据策略
  - 白名单自动判定
  - graph 消费产物约束

## 8. Success Metrics

- 结构指标：`service.py` 与 `graph_service.py` 中重复 graph 命名规则消除（单一策略源）。
- 配置指标：至少一部样书使用 `graph_profile.json` 完成人物种子/别名管理，无需代码补丁。
- 质量指标：新增迁移测试全部通过，且现有关键回归测试通过。
- 结果指标：样书图谱中核心角色 canonical/aliases 归并正确，假名噪声明显下降（可通过评估样例对比验证）。

## 9. Open Questions

- 白名单的判定维度具体基于哪些字段（`book_id`、来源标签、元数据）最终定稿？
- `graph_profile.json` 的最小可用字段集是否必须包含 seeds，还是允许完全空文件仅做人工修正钩子？
- “场景证据”的算法定义与阈值是否统一全书，还是允许在 profile 中按书覆盖？
- `character_card` 与 `event_timeline` 的字段契约是否需要在本期同步固化为 schema？
