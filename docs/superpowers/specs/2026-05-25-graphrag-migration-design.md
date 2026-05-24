# fanren-novel-system 完整迁移到 Microsoft GraphRAG 结构的改造方案（修订版）

> 版本：v2.0（基于 v1.0 审计修订）
> 修订日期：2026-05-25
> 目标项目：`fanren-novel-system`（小王一号）
> 本地 GraphRAG 源码目录：`D:\pythonProject\graphrag`
> 本地 GraphRAG 版本：**v3.0.9**（monorepo 结构）
> 目标定位：舍弃防剧透功能，将当前"中文小说 RAG + 人物图谱补丁"重构为"以 Microsoft GraphRAG 官方知识模型和查询模式为核心的中文长篇小说全书分析系统"。

---

## 0. 方案边界与关键结论

### 0.1 这次不是 GraphRAG-lite

本方案要求完全改成 GraphRAG 结构，不再保留旧的 RAG 主链路作为核心能力。后续主索引围绕 GraphRAG 知识模型组织：

```text
documents
text_units
entities
relationships
covariates
communities
community_reports
text/entity/report embeddings
```

旧产物不再作为问答主索引：

```text
chapter_chunks.json
chapter_summaries.json
event_timeline.json
character_card.json
character_registry.json
relationship_graph.json
world_rule.json
canon_memory.json
recent_plot.json
style_samples.json
TF-IDF payload
FAISS corpus-by-corpus index
```

### 0.2 舍弃防剧透后的新定位

新定位：

```text
全书分析工具：基于整本小说完整语料，回答人物、势力、事件、设定、主线、因果链等问题。
```

以下能力删除或废弃：

```text
scope_filter / spoiler_guard / chapter visibility filter / prefix index
allowed_text_units filter / allowed_entities filter / allowed_relationships filter
chapter_scope 参数驱动的检索过滤
```

### 0.3 本地 GraphRAG 实际结构（v1.0 方案修正）

**重要修正**：本地 GraphRAG 是 monorepo 结构，不是单包。

```text
D:\pythonProject\graphrag\
├── pyproject.toml                    # monorepo root (graphrag-monorepo)
├── packages/
│   ├── graphrag/                     # 主包 v3.0.9
│   │   ├── pyproject.toml
│   │   └── graphrag/
│   │       ├── __main__.py
│   │       ├── api/
│   │       │   ├── index.py          # Python API: indexing
│   │       │   └── query.py          # Python API: query (local/global/drift/basic)
│   │       ├── cli/
│   │       │   ├── main.py           # CLI 入口 (Typer app)
│   │       │   ├── index.py
│   │       │   └── query.py
│   │       ├── config/
│   │       │   ├── models/graph_rag_config.py
│   │       │   ├── init_content.py   # settings.yaml 模板
│   │       │   └── load_config.py
│   │       ├── data_model/           # entities, relationships, communities 等
│   │       ├── index/operations/     # extract_graph, extract_covariates 等
│   │       └── query/
│   │           ├── factory.py        # get_local/global/drift/basic_search_engine
│   │           └── indexer_adapters.py
│   ├── graphrag-llm/                 # LLM 抽象层（LiteLLM）
│   ├── graphrag-cache/
│   ├── graphrag-chunking/
│   ├── graphrag-common/
│   ├── graphrag-input/
│   ├── graphrag-storage/
│   └── graphrag-vectors/
```

关键发现：
- CLI 入口：`graphrag.cli.main:app`（Typer）
- Python API：`graphrag.api.index` / `graphrag.api.query`（标注 "under development"）
- LLM 层：基于 **LiteLLM**，支持任何 OpenAI-compatible endpoint
- 配置模型：`completion_models` + `embedding_models` 字典，每个 workflow 引用 model_id
- Python 要求：>=3.11,<3.14

### 0.4 集成策略决定

| 组件 | 集成方式 | 理由 |
|------|----------|------|
| Indexing | CLI (subprocess) | 长任务，隔离性好，失败不影响主进程 |
| Query | Python API (import) | 需要结构化结果，async 适配 FastAPI |
| Embedding | 本地 OpenAI-compatible server | 用中文模型，GraphRAG 通过 api_base 调用 |
| LLM (chat) | MiniMax via LiteLLM | settings.yaml 配置 api_base + api_key |

### 0.5 settings.yaml 模型配置模板

```yaml
completion_models:
  default_completion_model:
    model_provider: openai
    model: MiniMax-m2.7-HighSpeed
    api_base: "https://api.minimax.chat/v1"
    api_key: ${MINIMAX_API_KEY}
    auth_method: api_key
    retry:
      type: exponential_backoff

embedding_models:
  default_embedding_model:
    model_provider: openai
    model: Qwen/Qwen3-Embedding-4B
    api_base: "http://localhost:8000/v1"
    api_key: EMPTY
    auth_method: api_key
```

### 0.6 前置条件

1. Python >=3.11
2. 本地 GraphRAG 已安装：`pip install -e D:\pythonProject\graphrag\packages\graphrag`
3. 本地 embedding server 运行在 `http://localhost:8000/v1`（支持 `/v1/embeddings`）
4. MiniMax API key 可用

---

## 1. 当前项目问题定位

### 1.1 当前项目主链路不是 GraphRAG

当前主结构：

```text
小说 TXT
  -> 章节解析
  -> chunks / summaries / event_timeline / character_card / relationship_graph
  -> TF-IDF / FAISS / 规则匹配 / 伪图谱补丁
  -> QA / 续写 / 图谱展示
```

目标结构：

```text
小说 TXT
  -> GraphRAG workspace
  -> GraphRAG input
  -> settings.yaml
  -> GraphRAG indexing (CLI)
  -> output parquet tables
  -> GraphRAG query engine (Python API)
  -> QA / 图谱投影 / 时间线投影 / 全书分析
```

### 1.2 当前需要重点替换的文件

```text
novel_system/services/indexing.py    # _run_book_index() 构建旧 corpora
novel_system/services/qa.py          # ask() 调用 HybridRetriever + scope guard
novel_system/search/orchestrator.py  # 混合检索 + 图谱伪文档
novel_system/retrieval.py            # HybridRetriever
novel_system/indexing/vector_indexing.py  # TF-IDF + FAISS
novel_system/validator.py            # SpoilerGuard
novel_system/planner.py              # scope 相关规划
```

---

## 2. 最终目标目录结构

### 2.1 目标代码目录

```text
novel_system/
├── graphrag_app/
│   ├── __init__.py
│   ├── paths.py                  # GraphRAG workspace 路径管理
│   ├── workspace.py              # 每本书一个 GraphRAG workspace
│   ├── input_builder.py          # 小说 TXT/章节 -> GraphRAG input/*.txt
│   ├── settings_builder.py       # 生成 GraphRAG settings.yaml
│   ├── prompt_manager.py         # 管理小说领域 prompts
│   ├── index_runner.py           # 调用本地 GraphRAG indexing (CLI subprocess)
│   ├── table_loader.py           # 读取 output parquet
│   ├── table_validator.py        # 验证输出表是否完整
│   ├── query_router.py           # local/global/drift/basic 路由
│   ├── query_engine.py           # GraphRAG 查询统一入口 (Python API)
│   ├── answer_adapter.py         # GraphRAG 查询结果 -> AskResponse
│   ├── graph_projector.py        # entities/relationships -> 前端图谱
│   ├── timeline_projector.py     # covariates/text_units/documents -> 时间线
│   └── debug_dump.py             # 调试输出 tables、context、trace
│
├── services/
│   ├── indexing.py               # 改造：调用 graphrag_app.index_runner
│   ├── qa.py                     # 改造：调用 graphrag_app.query_engine
│   ├── continuation.py           # 第二阶段再改造，可暂时降级
│   └── stats.py                  # 改造：统计 GraphRAG workspace
│
├── legacy/
│   ├── README.md
│   └── old_rag/
│       ├── search/
│       ├── indexing/
│       ├── retrieval.py
│       ├── semantic_scorer.py
│       └── notes.md
```

### 2.2 目标数据目录

```text
data/
└── books/
    └── {book_id}/
        ├── source/
        │   └── original.txt
        ├── manifest.json
        ├── graphrag/
        │   ├── input/
        │   │   ├── chapter_0001.txt
        │   │   ├── chapter_0002.txt
        │   │   └── ...
        │   ├── settings.yaml
        │   ├── prompts/
        │   │   ├── entity_extraction.txt
        │   │   ├── summarize_descriptions.txt
        │   │   ├── claim_extraction.txt
        │   │   ├── community_report.txt
        │   │   └── query_system_prompt.txt
        │   ├── output/
        │   │   ├── documents.parquet
        │   │   ├── text_units.parquet
        │   │   ├── entities.parquet
        │   │   ├── relationships.parquet
        │   │   ├── covariates.parquet
        │   │   ├── communities.parquet
        │   │   └── community_reports.parquet
        │   ├── cache/
        │   └── logs/
        └── derived/
            ├── graph_view.json
            ├── timeline_view.json
            ├── table_stats.json
            └── debug_samples/
```

---

## 3. Phase 0：迁移前审计与冻结

### 3.1 目标

固定当前项目状态，确认 GraphRAG 本地源码结构，建立迁移文档和回滚点。确认本地 embedding server 可用。

### 3.2 要增加什么

新增文档：

```text
docs/GraphRAG迁移执行记录.md
docs/GraphRAG本地源码审计.md
docs/GraphRAG迁移风险清单.md
```

`docs/GraphRAG本地源码审计.md` 必须记录：

```text
1. D:\pythonProject\graphrag 的 monorepo 目录结构
2. GraphRAG package root: packages/graphrag/graphrag/
3. CLI 入口: graphrag.cli.main:app (Typer)
4. Python API 入口: graphrag.api.index / graphrag.api.query
5. Local/Global/DRIFT/Basic Search 的工厂函数位置: graphrag.query.factory
6. settings.yaml 模板位置: graphrag.config.init_content
7. output parquet 文件实际命名
8. 当前版本 v3.0.9，Python >=3.11
9. LLM 层使用 LiteLLM，支持 api_base 自定义
10. 本地 embedding server 验证结果
```

新增脚本：

```text
scripts/audit_graphrag_local.py
scripts/verify_embedding_server.py
```

### 3.3 要修改什么

修改 `README.md`，加迁移说明区：

```text
## GraphRAG Migration Notice

当前项目正在从旧混合检索架构迁移到 Microsoft GraphRAG v3 结构。
迁移期间 legacy RAG 仅作为回滚参考，不再新增功能。
```

### 3.4 要删除什么

此阶段不删除代码，只做冻结。

### 3.5 验收标准

```text
1. docs/GraphRAG本地源码审计.md 存在且能回答 init/index/query 调用方式
2. pip install -e packages/graphrag 成功，python -c "import graphrag" 无报错
3. graphrag CLI 可用：graphrag --help
4. 本地 embedding server 响应正常
5. git tag v-pre-graphrag-migration 已打
```

---

## 4. Phase 1：依赖、配置和项目入口改造

### 4.1 目标

让项目能识别 GraphRAG，具备创建 workspace、生成 settings、调用 index 的基础条件。

### 4.2 要增加什么

新增配置字段到 `novel_system/config.py` 的 `AppConfig`：

```python
# GraphRAG 配置
graphrag_workspace_name: str = "graphrag"
graphrag_use_cli_for_index: bool = True
graphrag_python_executable: str = "graphrag"
graphrag_index_timeout_sec: int = 7200
graphrag_default_search_mode: str = "auto"
graphrag_enable_claims: bool = True
graphrag_embedding_api_base: str = "http://localhost:8000/v1"
graphrag_embedding_model: str = "Qwen/Qwen3-Embedding-4B"
graphrag_chat_model: str = "MiniMax-m2.7-HighSpeed"
graphrag_chat_api_base: str = "https://api.minimax.chat/v1"
```

新增 `.env.example` 项：

```env
# GraphRAG 配置
GRAPHRAG_INDEX_TIMEOUT_SEC=7200
GRAPHRAG_CHAT_MODEL=MiniMax-m2.7-HighSpeed
GRAPHRAG_CHAT_API_BASE=https://api.minimax.chat/v1
GRAPHRAG_API_KEY=${MINIMAX_API_KEY}
GRAPHRAG_EMBEDDING_MODEL=Qwen/Qwen3-Embedding-4B
GRAPHRAG_EMBEDDING_API_BASE=http://localhost:8000/v1
```

新增：

```text
novel_system/graphrag_app/__init__.py
novel_system/graphrag_app/paths.py
novel_system/graphrag_app/workspace.py
```

`paths.py`：

```python
def book_root(config, book_id) -> Path
def graphrag_root(config, book_id) -> Path
def graphrag_input_dir(config, book_id) -> Path
def graphrag_output_dir(config, book_id) -> Path
def graphrag_settings_path(config, book_id) -> Path
def derived_dir(config, book_id) -> Path
```

`workspace.py`：

```python
class GraphRAGWorkspace:
    def prepare(self, book_id: str, source_path: Path) -> None
    def exists(self, book_id: str) -> bool
    def clear(self, book_id: str) -> None
    def status(self, book_id: str) -> dict
```

### 4.3 要修改什么

修改 `requirements.txt` / `pyproject.toml`，增加：

```text
pandas>=2.0
pyarrow>=14.0
pyyaml>=6.0
```

注意：`graphrag` 本身通过 editable install 引入，不写在 requirements.txt 中。

修改 `novel_system/service.py`，在初始化处增加：

```python
self.graphrag_workspace = GraphRAGWorkspace(self.config)
```

### 4.4 要删除什么

此阶段不删除旧 RAG，只在以下文件头部加 deprecated 注释：

```text
novel_system/retrieval.py
novel_system/search/orchestrator.py
novel_system/search/profiles.py
novel_system/indexing/vector_indexing.py
```

### 4.5 验收标准

```powershell
python -c "from novel_system.config import AppConfig; c=AppConfig.load(); print(c.graphrag_chat_model)"
python -c "from novel_system.graphrag_app.workspace import GraphRAGWorkspace; print('ok')"
```

无报错。

---

## 5. Phase 2：GraphRAG input 构建替换旧 chapter_chunks

### 5.1 目标

把小说 TXT 标准化写入 GraphRAG workspace 的 `input/*.txt`，用 GraphRAG 的 TextUnit 机制替代旧 `chapter_chunks`。

### 5.2 要增加什么

新增：

```text
novel_system/graphrag_app/input_builder.py
novel_system/graphrag_app/table_validator.py
```

`input_builder.py` 核心类：

```python
class GraphRAGInputBuilder:
    def build_from_txt(self, book_id: str, source_path: Path) -> dict:
        """
        读取原始 TXT，解析章节，写入 graphrag/input/chapter_XXXX.txt。
        返回 chapter_count、input_files、total_chars。
        """
```

输入文件格式（纯文本注释，不用 YAML front matter）：

```text
# book_id: fanren
# chapter_index: 1
# chapter_title: 第一章 山边小村

正文……
```

### 5.3 要修改什么

修改 `novel_system/indexing/parser.py`：保留 `parse_chapters()` 函数，但它现在只为 `GraphRAGInputBuilder` 服务。

修改 `novel_system/services/indexing.py`：在 `_run_book_index()` 中，旧流程替换为：

```python
input_stats = self.graphrag_input_builder.build_from_txt(book_id, source_path)
self.set_book_indexing(book_id, "indexing", 0.20)
```

暂时保留 `chapters.json` 用于前端 reader，但不参与 RAG。

### 5.4 要删除什么

从 `_run_book_index()` 主链路删除调用（不物理删除方法）：

```text
repo._build_chunks / _build_chapter_summaries / _build_event_timeline
_build_character_cards / _build_character_registry / _build_relationships
_build_world_rules / _build_canon_memory / _build_style_samples / _build_recent_plot_docs
```

### 5.5 验收标准

```powershell
Get-ChildItem data/books/{book_id}/graphrag/input/*.txt | Measure-Object
```

数量等于章节数。

---

## 6. Phase 3：GraphRAG settings.yaml 与小说领域 Prompt 接入

### 6.1 目标

为每本书生成 GraphRAG 可运行配置，配置小说领域实体类型和抽取提示词。

### 6.2 要增加什么

新增：

```text
novel_system/graphrag_app/settings_builder.py
novel_system/graphrag_app/prompt_manager.py
novel_system/graphrag_app/prompts/
    entity_extraction.txt
    claim_extraction.txt
    community_report.txt
    summarize_descriptions.txt
    query_system_prompt.txt
```

小说实体类型：

```text
person        人物
organization  门派、宗族、势力、组织、商会、帮派
location      村庄、山谷、洞府、门派驻地、秘境、城市
event         战斗、收徒、交易、逃亡、突破、试炼、阴谋
item          法宝、丹药、书籍、材料、信物、关键道具
technique     功法、法术、秘术、武技、阵法
rule          世界观规则、修炼规则、门规、交易规则、禁忌
```

`settings_builder.py` 生成的 settings.yaml 必须包含：

```yaml
input:
  base_dir: ./input

output:
  base_dir: ./output

cache:
  base_dir: ./cache

reporting:
  base_dir: ./logs

completion_models:
  default_completion_model:
    model_provider: openai
    model: MiniMax-m2.7-HighSpeed
    api_base: "https://api.minimax.chat/v1"
    api_key: ${MINIMAX_API_KEY}
    auth_method: api_key
    rate_limit:
      type: sliding_window
      requests_per_minute: 30

embedding_models:
  default_embedding_model:
    model_provider: openai
    model: Qwen/Qwen3-Embedding-4B
    api_base: "http://localhost:8000/v1"
    api_key: EMPTY
    auth_method: api_key

extract_graph:
  entity_types:
    - person
    - organization
    - location
    - event
    - item
    - technique
    - rule

extract_claims:
  enabled: true

embed_text:
  enabled: true
```

**重要**：settings 的真实字段必须对照 `D:\pythonProject\graphrag\packages\graphrag\graphrag\config\models\graph_rag_config.py` 生成。AI 助手执行时必须先读取该文件确认字段名。

### 6.3 要修改什么

修改 `.env.example` 和 `README.md`，说明 settings.yaml 由代码自动生成。

### 6.4 要删除什么

废弃旧抽取 prompt（`indexing/llm_extraction.py` 中面向 character/event/relationship 的旧 prompt）。如有依赖先移到 `legacy/`。

### 6.5 验收标准

```powershell
Test-Path data/books/{book_id}/graphrag/settings.yaml
Test-Path data/books/{book_id}/graphrag/prompts/entity_extraction.txt
```

且 settings.yaml 包含 completion_models、embedding_models、extract_graph 配置。

---

## 7. Phase 4: GraphRAG indexing runner 替换旧索引服务

### 7.1 目标

`POST /api/books/{book_id}/start-index` 不再构建旧 corpora，而是运行 GraphRAG index（CLI subprocess），产出官方 parquet 表。

### 7.2 要增加什么

新增：

```text
novel_system/graphrag_app/index_runner.py
novel_system/graphrag_app/table_loader.py
```

`index_runner.py` 核心接口：

```python
class GraphRAGIndexRunner:
    def run(self, book_id: str, force: bool = False) -> dict:
        """
        调用 GraphRAG CLI 执行 indexing。
        使用 subprocess 隔离，支持超时控制。
        """
```

CLI 调用方式（基于本地 v3.0.9 确认）：

```python
subprocess.run(
    ["graphrag", "index", "--root", str(workspace_root)],
    env=env,
    timeout=config.graphrag_index_timeout_sec,
    check=True,
    capture_output=True,
    text=True,
)
```

注意：`graphrag` 命令来自 `pip install -e packages/graphrag` 后注册的 console_scripts。如果未安装，fallback 为 `python -m graphrag index --root ...`。

`table_loader.py` 文件名兼容：

```python
TABLE_ALIASES = {
    "documents": ["documents.parquet", "create_final_documents.parquet"],
    "text_units": ["text_units.parquet", "create_final_text_units.parquet"],
    "entities": ["entities.parquet", "create_final_entities.parquet"],
    "relationships": ["relationships.parquet", "create_final_relationships.parquet"],
    "communities": ["communities.parquet", "create_final_communities.parquet"],
    "community_reports": ["community_reports.parquet", "create_final_community_reports.parquet"],
    "covariates": ["covariates.parquet", "create_final_covariates.parquet"],
}

class GraphRAGTableLoader:
    def load(self, book_id: str, table_name: str) -> pd.DataFrame
    def load_all(self, book_id: str) -> dict[str, pd.DataFrame]
    def exists(self, book_id: str, table_name: str) -> bool
```

### 7.3 要修改什么

修改 `novel_system/services/indexing.py`，将 `_run_book_index()` 改成：

```python
def _run_book_index(self, book_id: str) -> None:
    try:
        self.set_book_indexing(book_id, "indexing", 0.02)
        manifest = next((b for b in self.repo.list_books() if b["id"] == book_id), None)
        source_path = Path(manifest["source_path"])

        self.graphrag_workspace.prepare(book_id, source_path)
        self.set_book_indexing(book_id, "indexing", 0.10)

        self.graphrag_input_builder.build_from_txt(book_id, source_path)
        self.set_book_indexing(book_id, "indexing", 0.20)

        self.graphrag_settings_builder.build(book_id)
        self.set_book_indexing(book_id, "indexing", 0.30)

        result = self.graphrag_index_runner.run(book_id)
        self.set_book_indexing(book_id, "indexing", 0.85)

        self.graphrag_table_validator.validate(book_id)
        self.set_book_indexing(book_id, "indexing", 0.92)

        self.graph_projector.build(book_id)
        self.timeline_projector.build(book_id)
        self.set_book_indexing(book_id, "ready", 1.0)

    except Exception as exc:
        logger.exception("GraphRAG indexing failed for %s", book_id)
        self.set_book_indexing(book_id, "error", 0.0)
```

修改 `novel_system/models.py`，`BookInfo` 增加：

```python
text_unit_count: int = 0
entity_count: int = 0
relationship_count: int = 0
community_count: int = 0
```

### 7.4 要删除什么

从 `services/indexing.py` 主链路删除：

```text
build_vector_payload / build_vector_indexes
corpora JSON 写入循环
TF-IDF pickle 保存 / FAISS per corpus 保存
```

### 7.5 验收标准

索引完成后存在 parquet 表：

```powershell
Get-ChildItem data/books/{book_id}/graphrag/output/*.parquet | Select-Object Name
```

输出包含 entities.parquet, relationships.parquet, communities.parquet 等。

---

## 8. Phase 5: GraphRAG Query Engine 替换旧 HybridRetriever + 删除防剧透

### 8.1 目标

`services/qa.py` 不再通过 HybridRetriever 检索旧 corpus，改为调用 GraphRAG Python API。同时彻底移除防剧透/scope guard 逻辑（原方案 Phase 7 合并至此）。

### 8.2 要增加什么

新增：

```text
novel_system/graphrag_app/query_router.py
novel_system/graphrag_app/query_engine.py
novel_system/graphrag_app/answer_adapter.py
```

`query_router.py`：

```python
class GraphRAGQueryRouter:
    def route(self, query: str, requested_mode: str | None = None) -> str:
        """
        返回 local/global/drift/basic。
        路由规则：
        - local: 人物、地点、物品、功法、势力、关系、某个实体相关
        - global: 全书主题、主线、势力格局、人物群像、整体总结
        - drift: 复杂因果、多跳推理、人物动机、局部+全局
        - basic: 原文定位、具体情节、某句话附近
        """
```

`query_engine.py`（使用 Python API）：

```python
from graphrag.api.query import local_search, global_search
from graphrag.config.load_config import load_config

class GraphRAGQueryEngine:
    async def search(self, book_id: str, query: str, mode: str = "auto", **kwargs) -> GraphRAGQueryResult:
        """
        1. 加载 GraphRAG config (from workspace settings.yaml)
        2. 加载 output parquet tables as DataFrames
        3. 调用对应的 search 函数
        4. 返回统一结果
        """
```

`answer_adapter.py`：

```python
class GraphRAGAnswerAdapter:
    def to_ask_response(self, result: GraphRAGQueryResult) -> AskResponse:
        """将 GraphRAG (response, context) 转成原 API 的 AskResponse。"""
```

### 8.3 要修改什么

修改 `novel_system/services/qa.py`，将 `ask()` 改为 async 并重写主体：

```python
async def ask(self, book_id: str, request: AskRequest) -> AskResponse:
    trace_id = TraceLogger.generate_trace_id()
    start_time = time.perf_counter()

    self.ensure_indexed(book_id)

    mode = self.graphrag_query_router.route(
        request.user_query,
        requested_mode=getattr(request, "search_mode", None),
    )

    result = await self.graphrag_query_engine.search(
        book_id=book_id,
        query=request.user_query,
        mode=mode,
        conversation_history=request.conversation_history,
    )

    response = self.graphrag_answer_adapter.to_ask_response(result)

    if request.debug:
        response.trace = {
            "trace_id": trace_id,
            "search_mode": mode,
            "matched_entities": result.matched_entities,
            "used_community_reports": result.used_community_reports,
            "used_text_units": result.used_text_units,
            "duration_ms": int((time.perf_counter() - start_time) * 1000),
        }

    return response
```

注意：`ask()` 变成 async，因为 GraphRAG Python API 是 async 的。FastAPI 天然支持。

修改 `novel_system/models.py`，`AskRequest` 改为：

```python
class AskRequest(BaseModel):
    user_query: str
    conversation_history: list[dict] = []
    top_k: int = 6
    debug: bool = False
    search_mode: Literal["auto", "local", "global", "drift", "basic"] = "auto"
    # scope 保留但标记废弃，不参与任何逻辑
    scope: Scope = Field(default_factory=Scope)
```

修改 `novel_system/validator.py`：
- 移除 SpoilerGuard class
- 移除 scope_guard / future_query_blocked 相关逻辑
- 保留 Evidence Gate 和 Answer Validator，输入改为 GraphRAG query result

修改 `novel_system/api.py`：`/api/books/{book_id}/ask` handler 改为 async。

### 8.4 要删除什么

从 `services/qa.py` 删除：

```text
_retrieve / _retrieve_with_rewrite / _compute_query_embedding
_is_future_query_blocked / _scope_guard_answer / _known_state_evidence
_is_unknown_person_query / FUTURE_QUERY_RE
HybridRetriever 相关 import
所有 scope.chapters 过滤逻辑
```

迁移到 legacy：

```text
novel_system/retrieval.py -> novel_system/legacy/old_rag/
novel_system/search/ -> novel_system/legacy/old_rag/search/
novel_system/semantic_scorer.py -> novel_system/legacy/old_rag/
```

### 8.5 验收标准

local search 和 global search 均可用，trace 中包含 GraphRAG 结构化信息。

全局搜索确认防剧透已清除：

```powershell
Select-String -Path novel_system\**\*.py -Pattern "spoiler|future_query|scope_guard|chapter_scope" -Exclude *legacy*
```

结果为空或仅有 deprecated 注释。

---

## 9. Phase 6: 图谱、时间线全部改为 GraphRAG 派生视图

### 9.1 目标

前端图谱和时间线从 GraphRAG parquet 表投影生成，不再读旧 JSON。

### 9.2 要增加什么

新增：

```text
novel_system/graphrag_app/graph_projector.py
novel_system/graphrag_app/timeline_projector.py
```

`graph_projector.py`：

```python
class GraphRAGGraphProjector:
    def build(self, book_id: str) -> Path:
        """读取 entities.parquet + relationships.parquet -> derived/graph_view.json"""

    def get_interactive_graph(self, book_id: str, center: str | None, limit: int) -> dict:
        """返回前端力导向图的 nodes/edges"""
```

`timeline_projector.py`：

```python
class GraphRAGTimelineProjector:
    def build(self, book_id: str) -> Path:
        """优先读 covariates.parquet；不存在则从 text_units + entities 派生粗粒度 timeline"""
```

### 9.3 要修改什么

- `novel_system/graph_service.py`：替换为调用 `graph_projector.get_interactive_graph()`
- `novel_system/services/stats.py`：统计 GraphRAG 表行数
- `novel_system/api.py`：graph/timeline endpoint 改为返回 GraphRAG 派生数据

### 9.4 验收标准

```text
data/books/{book_id}/derived/graph_view.json 存在
data/books/{book_id}/derived/timeline_view.json 存在
GET /api/books/{book_id}/graph 和 /timeline 返回 GraphRAG 派生数据
```

---

## 10. Phase 7: 清理旧 RAG 主链路

### 10.1 目标

物理清理或隔离旧 RAG 文件，降低项目复杂度。

### 10.2 移动到 legacy

```text
novel_system/search/ -> novel_system/legacy/old_rag/search/
novel_system/retrieval.py -> novel_system/legacy/old_rag/
novel_system/semantic_scorer.py -> novel_system/legacy/old_rag/
novel_system/indexing/vector_indexing.py -> novel_system/legacy/old_rag/indexing/
novel_system/indexing/artifact_builders.py -> novel_system/legacy/old_rag/indexing/
novel_system/indexing/llm_extraction.py -> novel_system/legacy/old_rag/indexing/
novel_system/indexing/scene.py -> novel_system/legacy/old_rag/indexing/
```

### 10.3 删除旧运行时产物

```text
data/books/{book_id}/chapter_chunks.json
data/books/{book_id}/chapter_summaries.json
data/books/{book_id}/event_timeline.json
data/books/{book_id}/character_card.json
data/books/{book_id}/character_registry.json
data/books/{book_id}/relationship_graph.json
data/books/{book_id}/world_rule.json
data/books/{book_id}/canon_memory.json
data/books/{book_id}/recent_plot.json
data/books/{book_id}/style_samples.json
```

### 10.4 清理依赖

确认非 legacy 主链路无引用后删除：scikit-learn, jieba, faiss-cpu。
注意：networkx 不能删，GraphRAG v3 自身依赖它。

### 10.5 验收标准

主链路无旧 RAG 引用，pytest 和 API 启动正常。

---

## 11. Phase 8: 测试体系重建

### 11.1 目标

旧测试围绕 chunk、character registry、search orchestrator、spoiler guard；迁移后改成 GraphRAG workspace、tables、query、derived views 的测试。

### 11.2 要增加什么

新增测试：

```text
tests/graphrag_app/
+-- test_workspace.py
+-- test_input_builder.py
+-- test_settings_builder.py
+-- test_index_runner_smoke.py
+-- test_table_loader.py
+-- test_table_validator.py
+-- test_query_router.py
+-- test_query_engine_contract.py
+-- test_answer_adapter.py
+-- test_graph_projector.py
+-- test_timeline_projector.py
```

测试重点：
1. input_builder 能把 TXT 拆成 input/chapter_XXXX.txt
2. settings_builder 能生成有效 settings
3. table_loader 能兼容两类 parquet 命名
4. query_router 能正确区分 local/global/drift/basic
5. answer_adapter 能把 GraphRAG result 转成 AskResponse
6. graph_projector 能从 entities/relationships 生成前端图谱
7. timeline_projector 能从 covariates 或 text_units 生成时间线

### 11.3 要修改什么

修改旧测试文件，新断言围绕 GraphRAG 结构。

### 11.4 要删除什么

删除或移动到 tests/legacy/：

```text
tests/test_search_orchestrator.py
tests/test_character_registry.py
tests/test_scene_segments.py
tests/test_tfidf_retrieval.py
tests/test_vector_store.py
tests/test_vector_retrieval.py
```

### 11.5 验收标准

```powershell
pytest tests/graphrag_app -v
```

通过。

---

## 12. Phase 9: 前端和 API 文档调整

### 12.1 目标

前端展示 GraphRAG 查询模式和全书分析能力，不再展示防剧透。

### 12.2 要修改什么

修改前端文件：

```text
static/app.js
templates/dashboard.html
```

删除或隐藏：章节范围输入框、防剧透提示、scope 相关控件。

新增：Search Mode 选择（Auto/Local/Global/DRIFT/Basic）、GraphRAG debug trace 展示。

修改 README.md，更新技术特性：

```text
GraphRAG 索引：基于 documents/text_units/entities/relationships/communities/community_reports
Local Search：人物、物品、功法、地点、关系类问题
Global Search：主题、主线、势力格局、人物群像
DRIFT Search：复杂因果、多跳推理、人物动机
Basic Search：原文片段定位
派生图谱：从 GraphRAG entities/relationships 生成
派生时间线：从 GraphRAG covariates/text_units 生成
```

### 12.3 验收标准

前端可以上传小说、启动索引、选择 query mode 提问、查看图谱和时间线。不再出现防剧透描述。

---

## 13. Phase 10: 续写功能处理

### 13.1 策略

分两步：
1. 主问答迁移期间，续写降级为"暂时不可用"或仅用 text_units 中的风格样例
2. GraphRAG 稳定后，续写改为：Basic Search 取风格样例 + Local Search 取人物设定 + DRIFT Search 取剧情上下文

### 13.2 要修改什么

修改 `novel_system/services/continuation.py`：如果旧 corpus 不存在，返回降级提示。

### 13.3 要删除什么

从续写主链路删除对 recent_plot / style_samples / canon_memory / world_rule / scope 的依赖。

---

## 14. Phase 11: 最终清理

### 14.1 代码清理

最终主链路中不应出现：

```text
SearchOrchestrator / HybridRetriever / TfidfVectorizer
build_vector_payload / chapter_scope / SpoilerGuard
_scope_guard_answer / _is_future_query_blocked
chapter_chunks / character_card / event_timeline / relationship_graph 作为主数据
```

允许出现位置：novel_system/legacy/、docs/、tests/legacy/

### 14.2 文档清理

更新所有 docs/ 下的项目文档，删除围绕旧架构的说明。

### 14.3 验收标准

```powershell
Select-String -Path novel_system\**\*.py -Pattern "SearchOrchestrator|HybridRetriever|TfidfVectorizer|chapter_chunks|character_card" -Exclude *legacy*
```

结果为空。

---

## 15. 建议的提交顺序

```text
commit 1:  docs: add GraphRAG migration audit documents (Phase 0)
commit 2:  chore: install graphrag editable, verify embedding server
commit 3:  config: add GraphRAG workspace configuration (Phase 1)
commit 4:  feat: add graphrag_app workspace/input/settings modules (Phase 2-3)
commit 5:  feat: add GraphRAG index runner and table loader (Phase 4)
commit 6:  refactor: replace indexing service with GraphRAG indexing (Phase 4)
commit 7:  feat: add GraphRAG query router and engine (Phase 5)
commit 8:  refactor: replace QA with GraphRAG query + remove spoiler guard (Phase 5)
commit 9:  feat: derive graph and timeline views from GraphRAG tables (Phase 6)
commit 10: cleanup: move old RAG modules to legacy (Phase 7)
commit 11: test: add GraphRAG app tests (Phase 8)
commit 12: docs+frontend: update for GraphRAG architecture (Phase 9)
```

---

## 16. 给 AI 助手的执行总 Prompt

```text
你现在是 fanren-novel-system 的 GraphRAG 架构迁移工程师。

关键信息：
- 本地 GraphRAG 源码：D:\pythonProject\graphrag（v3.0.9 monorepo）
- 主包位置：packages/graphrag/graphrag/
- CLI 入口：graphrag.cli.main:app (Typer)
- Python API：graphrag.api.index / graphrag.api.query（async）
- LLM 层：LiteLLM，支持 api_base 自定义
- 集成策略：indexing 用 CLI subprocess，query 用 Python API import
- Embedding：本地 OpenAI-compatible server (http://localhost:8000/v1)
- Chat LLM：MiniMax (https://api.minimax.chat/v1)

你必须先阅读并审计本地 GraphRAG 项目，不能凭空写接口。
请先完成 Phase 0 的审计产物，不要改业务代码。
```

---

## 17. 关键风险与规避

| 风险 | 规避措施 |
|------|----------|
| GraphRAG indexing 成本高 | 先用 3-5 章小样本跑通，再 20 章，最后全书 |
| 中文实体抽取质量不稳定 | 小说专用 prompt + 实体类型覆盖 7 类 + 要求保留中文原名 |
| 输出表命名与文档不同 | table_loader.py 支持别名映射 |
| 旧前端依赖 scope 和旧 graph/timeline | API 参数短期保留但忽略，返回结构兼容 |
| 续写功能迁移面过大 | 主问答迁移阶段先降级续写 |
| Python API 标注 "not stable" | 已确认 v3.0.9 是稳定 major version；如 API 变化，fallback 到 CLI query |
| Embedding server 不可用 | settings_builder 检查 server 健康，不可用时报错而非静默失败 |

---

## 18. 最终验收标准

迁移完成后必须满足：

```text
1. 一本小说可通过 /api/books 上传或注册
2. /api/books/{book_id}/start-index 创建 GraphRAG workspace 并运行 CLI indexing
3. data/books/{book_id}/graphrag/input 存在章节 txt
4. data/books/{book_id}/graphrag/settings.yaml 存在且配置正确
5. data/books/{book_id}/graphrag/output 存在 GraphRAG parquet 表
6. /api/books/{book_id}/ask 支持 search_mode=local/global/drift/basic
7. local 问题使用 entities/relationships/text_units
8. global 问题使用 community_reports
9. graph 接口来自 entities/relationships 派生视图
10. timeline 接口来自 covariates/text_units 派生视图
11. 主链路不再引用旧 RAG 组件
12. README 不再宣传防剧透和 TF-IDF
13. tests/graphrag_app 通过
14. legacy 中保留旧代码作为参考，主链路无依赖
```

---

## 19. 与 v1.0 方案的主要差异

| 项目 | v1.0 方案 | v2.0 修订 |
|------|-----------|-----------|
| GraphRAG 版本 | 未明确，假设单包 | v3.0.9 monorepo |
| 包结构 | graphrag/ 或 python/graphrag/ | packages/graphrag/graphrag/ |
| LLM 层 | 未确认兼容性 | LiteLLM，直接支持 api_base |
| 集成方式 | 全 CLI subprocess | 混合：indexing CLI + query Python API |
| Embedding | 未明确 | 本地 OpenAI-compatible server |
| 防剧透删除时机 | Phase 7（靠后） | Phase 5（与 query 替换合并） |
| Phase 总数 | 12 | 11（合并后更紧凑） |
| 模块粒度 | 15 文件 | 保持 15 文件（用户选择） |
| settings.yaml 格式 | 旧版 workflows 列表 | v3 的 completion_models/embedding_models 字典 |
