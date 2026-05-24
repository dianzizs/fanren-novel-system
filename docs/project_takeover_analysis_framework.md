# 项目接管分析框架

> 适用阶段：项目失控后的接管分析期。  
> 当前阶段只允许分析、盘点、分类、记录风险；不允许删除、重构、合并模块或新增功能。

## 1. 项目接管检查清单

### 1.1 冻结现场

接管第一步不是整理代码，而是确认当前事实。

必须检查：

- `git status --short`
  - 记录所有未提交代码改动。
  - 记录所有被删除的文档。
  - 记录所有新增但未纳入版本管理的文件。
- `.env`
  - 只检查配置键名和本地运行依赖。
  - 不复制、不外传、不写入公开文档。
- `.env.example`
  - 作为配置契约来源。
- `AGENTS.md`
  - 作为 AI 工作规则和运行命令约束来源。
- `README.md`
  - 只作为参考，不直接当作事实源。
  - 当前 README 存在编码乱码和入口滞后风险。

接管记录模板：

```md
当前工作区状态：干净 / 脏
未提交代码：有 / 无
未提交文档删除：有 / 无
README 与实际入口：一致 / 不一致
允许进入整理阶段：是 / 否
```

### 1.2 应该检查哪些目录

#### 必查目录

- `novel_system/`
  - 后端核心系统。
  - 需要建立模块地图、调用链和风险等级。
- `novel_system/services/`
  - 业务服务 mixin 层。
  - 需要判断职责拆分是否清晰。
- `novel_system/search/`
  - 检索编排、检索 profile、候选结果类型。
- `novel_system/vector_store/`
  - 向量存储抽象和 FAISS 实现。
- `novel_system/embedding/`
  - 本地 embedding provider。
- `novel_system/reranker/`
  - reranker 抽象和规则实现。
- `templates/`
  - Dashboard HTML。
- `static/`
  - 前端 JS / CSS。
- `tests/`
  - 当前系统行为规格的重要事实源。
- `scripts/`
  - 评测、迁移、运维脚本。
- `tasks/`
  - 历史 PRD，可能比 README 更接近真实演进。
- `docs/`
  - 当前需要重建文档基线。
- `.agents/`、`.claude/`、`.codex/`
  - AI 开发规则、skills、上下文持久化基础设施。

#### 谨慎检查目录

- `data/`
  - 可能包含评测数据、运行产物、报告。
  - 不能简单按“生成物”处理。
- `.worktrees/`
  - 可能包含隔离开发留下的工作树。
  - 删除前必须确认没有未保存工作。
- `__pycache__/`、`.pytest_cache/`
  - 通常是生成物，但本阶段只标记，不删除。

### 1.3 应该识别哪些入口文件

#### 运行入口

- `novel_system/api.py`
  - FastAPI 应用工厂 `create_app()`。
  - 路由集中定义。
- `start_server.py`
  - 直接通过 uvicorn 启动服务。
  - 需要确认是否为临时启动脚本。
- `novel_system/__init__.py`
  - 包入口。

#### 服务入口

- `novel_system/service.py`
  - `NovelSystemService`
  - `create_service()`
- `novel_system/graph_service.py`
  - 当前实际服务可能由 `create_service()` 返回。

#### 前端入口

- `templates/dashboard.html`
- `static/app.js`
- `static/styles.css`

#### 脚本入口

- `scripts/eval_retrieval.py`
- `scripts/run_full_eval.py`
- `scripts/verify_migration.py`
- `eval_runner_template.py`
- `show_trace.py`

入口分析模板：

```md
入口文件：
当前用途：
是否被 README 提及：
是否被 AGENTS.md 提及：
是否被测试覆盖：
是否保留：
风险：
```

### 1.4 应该分析哪些配置文件

- `AGENTS.md`
  - 项目级 AI 开发约束。
  - Python 命令必须使用 `conda run -n chaishu python ...`。
- `pyproject.toml`
  - pytest 配置。
  - 当前测试发现范围主要是 `tests/`。
- `requirements.txt`
  - Python 依赖。
- `.env.example`
  - MiniMax、Mimo、Embedding、Tracing、默认书籍配置。
- `.env`
  - 本地真实配置，只检查不泄露。
- `.gitignore`
  - 判断日志、缓存、运行数据、模型缓存是否被正确忽略。
- `.editorconfig`
  - 编码、换行、缩进规范。

配置矩阵模板：

```md
配置项：
来源文件：
默认值：
是否必需：
影响模块：
缺失时行为：
是否有测试：
```

### 1.5 应该梳理哪些核心模块

#### API 层

- `novel_system/api.py`

检查重点：

- 路由数量。
- 路由是否直接包含业务逻辑。
- 文件上传、书籍管理、索引启动、问答、续写、图谱、时间线是否混在一起。
- 前端页面和 API 是否耦合过深。

#### 服务层

- `novel_system/service.py`
- `novel_system/services/base.py`
- `novel_system/services/qa.py`
- `novel_system/services/continuation.py`
- `novel_system/services/indexing.py`
- `novel_system/services/stats.py`
- `novel_system/graph_service.py`

检查重点：

- `NovelSystemService` 是清晰门面，还是通过多重继承拼装出来的大对象。
- `GraphService` 为什么继承服务类，而不是组合。
- QA、continuation、indexing、stats 的边界是否明确。

#### 索引与产物层

- `novel_system/indexing.py`

检查重点：

- `BookIndexRepository`
- `LoadedBookIndex`
- `CharacterRegistryBuilder`
- `SceneSegmentBuilder`
- `build_chapter_chunks`
- `build_event_timeline`
- `build_character_cards`
- `build_book_artifacts`

需要画出：

```txt
原始小说文本
  -> 章节解析
  -> chapter_chunks
  -> character_card
  -> event_timeline
  -> graph/profile/vector index
```

#### 检索层

- `novel_system/retrieval.py`
- `novel_system/search/orchestrator.py`
- `novel_system/search/base.py`
- `novel_system/search/profiles.py`
- `novel_system/reranker/*`
- `novel_system/vector_store/*`

检查重点：

- sparse / dense / rerank / RRF 的顺序。
- `SearchOrchestrator` 与 `HybridRetriever` 的职责是否重叠。
- profile 是否承担渐进式披露和检索目标切换。

#### Planner / Query Rewrite 层

- `novel_system/planner.py`

检查重点：

- `RuleBasedPlanner`
- `QueryRewriter`
- `MemoryState`
- `PlannerOutput`
- 检索意图如何影响下游检索。

#### 验证层

- `novel_system/validator.py`
- `novel_system/entity_extractor.py`
- `novel_system/extraction_models.py`

检查重点：

- Evidence Gate。
- Answer Validator。
- Continuation Validator。
- Spoiler Guard。
- 实体一致性检查。

这是高风险模块，不能凭体感优化。

#### LLM 与 Embedding 层

- `novel_system/llm.py`
- `novel_system/embedding/*`
- `novel_system/semantic_scorer.py`

检查重点：

- MiniMax / Mimo fallback。
- 本地 embedding provider。
- embedding cache。
- 网络调用与本地模型调用如何被测试 mock。

#### 图谱层

- `novel_system/graph_service.py`
- `novel_system/graph_name_policy.py`

检查重点：

- name policy。
- whitelist。
- alias。
- graph profile。
- graph 产物与前端展示的关系。

#### 追踪与评测层

- `novel_system/tracing.py`
- `scripts/eval_retrieval.py`
- `scripts/run_full_eval.py`
- `data/eval/*`
- `data/eval_full/*`

检查重点：

- trace 是否能成为调试事实源。
- eval 数据是否可复现。
- report 是生成物还是基线产物。

### 1.6 应该判断哪些文件可能冗余

本阶段只能标记“疑似”，不能删除。

优先标记：

- `__pycache__/`
- `.pytest_cache/`
- `server.log`
- `server-8001.log`
- `server-8001.err.log`
- 根目录 `test_api.py`
- 根目录 `test_read_log.py`
- 根目录大体积小说文本：
  - `凡人修仙传(1-500章).txt`
  - `《诛仙》_qinkan.net.txt`
- `data/eval_full/report.html`
- `data/eval_full/report.json`
- `data/eval_full/report_summary.txt`
- `data/eval_full/predictions.jsonl`
- `eval_runner_template.py`
- `p0_test_cases.jsonl`
- `fanren_eval_cases_v1.jsonl`
- `fanren_eval_readme.md`
- `.agents/skills/ralph/archive/*`
- `.worktrees/*`

冗余判断模板：

```md
文件：
为什么疑似冗余：
谁引用它：
是否被测试使用：
是否是运行产物：
删除风险：
结论：
```

## 2. 文件分类标准

### 2.1 核心运行文件

定义：服务启动、业务主流程、核心领域逻辑依赖的文件。

当前项目包括：

- `novel_system/api.py`
- `novel_system/service.py`
- `novel_system/services/*.py`
- `novel_system/models.py`
- `novel_system/config.py`
- `novel_system/indexing.py`
- `novel_system/planner.py`
- `novel_system/retrieval.py`
- `novel_system/validator.py`
- `novel_system/llm.py`
- `novel_system/graph_service.py`
- `novel_system/graph_name_policy.py`
- `novel_system/tracing.py`
- `novel_system/semantic_scorer.py`
- `novel_system/novel_heuristics.py`

判定规则：

- 被 `api.py`、`service.py`、`tests/` 直接或间接引用。
- 删除会导致服务无法启动或核心 API 失效。
- 包含领域模型、索引、检索、验证、生成、图谱之一。

### 2.2 页面 / 路由文件

定义：HTTP 路由、页面模板、前端入口页面。

当前项目包括：

- `novel_system/api.py`
- `templates/dashboard.html`

注意：

- `api.py` 同时是路由文件和运行入口，属于高风险文件。
- `dashboard.html` 与 `static/app.js` 强耦合，需要一起分析。

### 2.3 组件文件

定义：前端可复用 UI 组件或后端可替换组件。

当前项目没有明显前端组件目录。

后端组件型文件包括：

- `novel_system/embedding/base.py`
- `novel_system/embedding/factory.py`
- `novel_system/embedding/local_cuda.py`
- `novel_system/embedding/local_openvino.py`
- `novel_system/reranker/base.py`
- `novel_system/reranker/factory.py`
- `novel_system/reranker/rule_based.py`
- `novel_system/vector_store/base.py`
- `novel_system/vector_store/faiss_store.py`

判定规则：

- 有 base / factory / implementation 结构。
- 可被替换。
- 不直接处理 HTTP 请求。

### 2.4 工具函数文件

定义：通用、低状态、可复用函数。

当前项目包括：

- `novel_system/utils/text_utils.py`
- `show_trace.py`
- `scripts/verify_migration.py`

谨慎项：

- `novel_system/novel_heuristics.py` 名义上像工具，但实际可能包含领域规则，不应简单归为工具。

### 2.5 接口 / 数据请求文件

定义：外部 API、模型服务、本地模型 provider、数据访问封装。

当前项目包括：

- `novel_system/llm.py`
- `novel_system/embedding/*`
- `novel_system/vector_store/*`
- `novel_system/indexing.py` 中的 `BookIndexRepository`

前端侧：

- `static/app.js`
  - 同时承担 UI 交互和 API 请求，需要进一步拆分标注。

### 2.6 状态管理文件

定义：保存或组织运行状态、会话状态、索引状态、任务状态。

当前项目包括：

- `novel_system/services/base.py`
- `novel_system/services/indexing.py`
- `novel_system/indexing.py`
- `novel_system/planner.py` 中的 `MemoryState`
- `novel_system/tracing.py`
- `data/` 下 runtime / eval 相关文件，视具体内容判断。

前端侧：

- `static/app.js`
  - 若内部维护当前 book、graph、indexing status、UI mode，也应归入状态管理观察对象。

### 2.7 样式文件

- `static/styles.css`

检查标准：

- 是否存在与 HTML 结构强耦合的选择器。
- 是否有未使用样式。
- 是否同时承担布局、状态、视觉全部职责。

### 2.8 配置文件

- `AGENTS.md`
- `.env`
- `.env.example`
- `.gitignore`
- `.gitattributes`
- `.editorconfig`
- `pyproject.toml`
- `requirements.txt`

高风险说明：

- `.env` 不进入版本库，不写入公开文档。
- `AGENTS.md` 是 AI 工作流约束，不是普通说明文档。

### 2.9 静态资源

- `static/app.js`
- `static/styles.css`
- 根目录小说 `.txt` 文件暂时也可标为原始静态数据，但不应长期放根目录。

### 2.10 测试文件

- `tests/test_*.py`
- 根目录：
  - `test_api.py`
  - `test_read_log.py`

注意：

- `pyproject.toml` 只配置了 `tests` 目录。
- 根目录测试文件可能不是正式测试套件的一部分，需要单独确认。

### 2.11 文档文件

- `README.md`
- `AGENTS.md`
- `tasks/*.md`
- `fanren_eval_readme.md`
- 当前 git 状态中被删除的 `docs/*`

接管判断：

- README 存在乱码和入口滞后风险。
- `tasks/` 可能比 `README.md` 更接近真实开发历史。
- `docs/` 当前是最高优先级修复对象之一，但接管初期应先重建文档基线。

### 2.12 疑似冗余文件

只能标记，不能删除。

候选：

- `__pycache__/`
- `.pytest_cache/`
- `server.log`
- `server-8001.log`
- `server-8001.err.log`
- 根目录临时测试文件：
  - `test_api.py`
  - `test_read_log.py`
- 根目录大体积小说文本。
- `data/eval_full/*` 报告产物。
- `.agents/skills/ralph/archive/*`
- `.worktrees/*`
- README 中提到但当前不存在的脚本对应说明。

### 2.13 高风险不可轻易删除文件

- `novel_system/indexing.py`
- `novel_system/validator.py`
- `novel_system/graph_name_policy.py`
- `novel_system/graph_service.py`
- `novel_system/services/*.py`
- `novel_system/models.py`
- `novel_system/api.py`
- `static/app.js`
- `templates/dashboard.html`
- `tests/*.py`
- `tasks/*.md`
- `AGENTS.md`
- `.agents/`
- `.claude/`
- `.codex/`
- `.env.example`
- `data/eval/*.jsonl`
- 当前 git 中显示删除的 `docs/*`

## 3. 后续文档目录建议

建议把 `docs/` 设计成渐进式披露目录：先看地图，再看模块，再看流程，再看细节。

```txt
docs/
  00_project_brief.md
  01_current_state.md
  02_entrypoints.md
  03_architecture_map.md
  04_module_inventory.md
  05_runtime_flows.md
  06_data_and_artifacts.md
  07_config_matrix.md
  08_api_contract.md
  09_frontend_dashboard.md
  10_testing_strategy.md
  11_eval_and_tracing.md
  12_ai_development_rules.md
  13_risk_register.md
  14_redundancy_candidates.md
  15_change_log.md
  baseline/
    modules.md
    config.md
    routes.md
    tests.md
  decisions/
    ADR-0001-doc-driven-workflow.md
  plans/
  specs/
```

### `00_project_brief.md`

作用：给新接手者 5 分钟内看懂项目。

内容：

- 项目是什么。
- 核心用户场景。
- 当前可运行能力。
- 当前不可信 / 待确认能力。
- 一句话架构。

### `01_current_state.md`

作用：冻结接管时刻的事实。

内容：

- git 状态。
- 未提交文件。
- 已删除文档。
- 当前入口。
- 当前测试状态。
- 当前已知风险。

### `02_entrypoints.md`

作用：统一入口认知。

内容：

- 服务启动入口。
- API 路由入口。
- 页面入口。
- 脚本入口。
- 测试入口。
- README / AGENTS / 实际文件之间的不一致。

### `03_architecture_map.md`

作用：项目架构总图。

示意：

```txt
Dashboard
  -> FastAPI routes
    -> NovelSystemService / GraphService
      -> QA / Continuation / Indexing / Stats
        -> Planner / Retrieval / Validator / LLM / Graph / Index Repository
```

需要包含：

- 模块关系。
- 数据流。
- 哪些模块是核心。
- 哪些模块是扩展能力。
- 哪些模块边界不清。

### `04_module_inventory.md`

作用：模块台账。

每个文件记录：

```md
文件：
职责：
被谁调用：
调用谁：
输入：
输出：
副作用：
测试覆盖：
风险等级：
是否可改：
```

### `05_runtime_flows.md`

作用：把核心流程讲清楚。

至少写 6 条流程：

- 启动服务流程。
- 导入书籍流程。
- 构建索引流程。
- 问答流程。
- 续写流程。
- 图谱展示流程。
- trace/debug 流程。

每条流程使用：

```md
入口：
步骤：
关键文件：
数据产物：
失败点：
测试：
```

### `06_data_and_artifacts.md`

作用：解释 `data/`、小说文本、索引产物、评测产物。

内容：

- 原始小说文本应该放哪里。
- 运行时索引在哪里。
- 评测数据在哪里。
- 哪些可再生成。
- 哪些是基线数据。
- 哪些不能提交。
- 哪些不能删除。

### `07_config_matrix.md`

作用：统一配置来源。

内容：

- `.env.example` 每个变量的含义。
- 必填 / 可选。
- 默认值。
- 影响模块。
- 本地开发配置。
- 测试配置。
- 生产配置。

### `08_api_contract.md`

作用：记录后端 API contract。

内容：

- 路由。
- 请求体。
- 响应体。
- 错误。
- 对应前端调用位置。
- 对应测试。

优先从 `novel_system/api.py` 生成事实，不从 README 抄。

### `09_frontend_dashboard.md`

作用：记录 Dashboard 的 DOM、状态和 API 关系。

内容：

- 页面区域。
- 用户动作。
- `static/app.js` 状态变量。
- API 调用。
- 图谱交互。
- 索引状态轮询。
- 当前耦合点。

### `10_testing_strategy.md`

作用：把测试变成接管护栏。

内容：

- 测试分类。
- 每类测试覆盖的模块。
- 哪些测试是快速 smoke。
- 哪些测试依赖外部模型 / 网络。
- 回归命令。
- 接管阶段禁止跳过哪些测试。

项目测试命令：

```bash
conda run -n chaishu python -m pytest
```

### `11_eval_and_tracing.md`

作用：把 trace 和 eval 变成分析工具，而不是散落脚本。

内容：

- trace 如何开启。
- trace 字段解释。
- eval 数据集。
- eval 脚本。
- report 是否可再生成。
- 如何用 trace 定位 retrieval / validator / LLM 问题。

### `12_ai_development_rules.md`

作用：把 AI 开发规则、文档驱动、小步修改、上下文持久化落地。

内容：

- 每次改动前必须读哪些文档。
- 每次改动后必须更新哪些文档。
- 什么规模需要 PRD。
- 什么规模需要 plan。
- 什么时候必须写测试。
- AI 禁止事项。
- 上下文交接格式。

### `13_risk_register.md`

作用：风险登记表。

格式：

```md
风险：
影响：
触发条件：
证据：
规避方式：
当前状态：
```

当前应记录：

- 文档被删除。
- README 乱码 / 滞后。
- 入口不一致。
- `indexing.py` 过大。
- `validator.py` 高复杂度。
- 前端 JS 集中。
- 根目录临时文件混杂。
- 数据 / 运行产物边界不清。
- 多套 AI 工具配置并存。

### `14_redundancy_candidates.md`

作用：冗余候选清单，不是删除清单。

格式：

```md
文件：
疑似原因：
引用证据：
测试证据：
运行证据：
删除风险：
处理建议：
```

结论只能是：

- 保留。
- 移动到归档。
- 加入 `.gitignore`。
- 后续删除。
- 暂缓判断。

### `15_change_log.md`

作用：接管期之后的文档化变更日志。

每次变更记录：

```md
日期：
目标：
改动文件：
验证命令：
文档更新：
风险：
回滚方式：
```

## 4. 禁止事项

本阶段 AI 绝对不允许：

- 不允许删除任何文件。
- 不允许恢复、覆盖、撤销用户未提交改动。
- 不允许重构。
- 不允许合并模块。
- 不允许拆分模块。
- 不允许新建功能。
- 不允许修改 API 行为。
- 不允许修改前端交互。
- 不允许修改测试来适配当前代码。
- 不允许格式化全仓库。
- 不允许批量移动文件。
- 不允许顺手清理日志、缓存、临时文件。
- 不允许凭文件名判断无用。
- 不允许凭 `rg` 搜不到引用就判定文件可删。
- 不允许把 README 当作事实源直接更新架构结论。
- 不允许把 `data/` 下内容全部视为生成物。
- 不允许读取或输出 `.env` 中的真实密钥。
- 不允许忽略 `AGENTS.md` 中的 conda 环境要求。
- 不允许绕过 `conda run -n chaishu python ...` 运行 Python 验证。
- 不允许将 `docs/` 当前删除状态视为正常。
- 不允许把 `.agents/`、`.claude/`、`.codex/` 当作无关目录删除。
- 不允许在未建立模块台账前做瘦身。
- 不允许在未建立测试护栏前做优化。
- 不允许在未确认入口一致性前改启动方式。
- 不允许在未确认数据产物来源前移动小说文本、eval 数据或 runtime 数据。
- 不允许在未写明证据的情况下给文件打冗余结论。

本阶段唯一允许的动作：

- 读取文件。
- 盘点目录。
- 记录入口。
- 标记风险。
- 建立分类。
- 建立文档目录方案。
- 输出接管分析结论。
