# NovelQA System — GraphRAG 全书分析系统

基于 Microsoft GraphRAG v3 构建的中文长篇小说全书分析系统。支持实体抽取、关系图谱、社区发现、多模式检索。

> **GraphRAG Migration Notice**: 本项目已从旧混合检索架构（TF-IDF + FAISS + 规则匹配）迁移到 Microsoft GraphRAG v3 结构。
> 旧 RAG 模块移至 `novel_system/legacy/` 作为参考，不在主链路使用。

## 功能特性

### 核心功能
- **GraphRAG 索引**: documents → text_units → entities → relationships → communities → community_reports
- **Local Search**: 人物、物品、功法、地点、关系类问题
- **Global Search**: 主题、主线、势力格局、人物群像
- **DRIFT Search**: 复杂因果、多跳推理、人物动机
- **Basic Search**: 原文片段定位
- **派生图谱**: 从 GraphRAG entities/relationships 生成力导向图
- **派生时间线**: 从 GraphRAG covariates/text_units 生成时间线

### 技术特性
- **GraphRAG v3.0.9**: Microsoft 官方知识图谱管道
- **多模式检索**: Local / Global / DRIFT / Basic 四种搜索模式
- **实体类型**: person / organization / location / event / item / technique / rule
- **离线 Embedding**: 本地 OpenAI-compatible embedding server
- **LLM**: MiniMax via LiteLLM (OpenAI-compatible API)

## 快速开始

### 环境要求
- Python >=3.11,<3.14
- conda 环境: `chaishu`
- Microsoft GraphRAG v3.0.9（已通过 editable install 安装）
- 本地 Embedding server (http://localhost:8000/v1)

### 安装依赖

```bash
python -m pip install -r requirements.txt
```

### 配置环境变量

创建 `.env` 文件：

```bash
copy .env.example .env
```

然后在 `.env` 中填入：

```env
MINIMAX_API_KEY=your_api_key_here
MINIMAX_BASE_URL=https://api.minimax.chat/v1
MINIMAX_CHAT_MODEL=MiniMax-m2.7-HighSpeed

# GraphRAG 配置
GRAPHRAG_INDEX_TIMEOUT_SEC=7200
GRAPHRAG_CHAT_MODEL=MiniMax-m2.7-HighSpeed
GRAPHRAG_CHAT_API_BASE=https://api.minimax.chat/v1
GRAPHRAG_API_KEY=${MINIMAX_API_KEY}
GRAPHRAG_EMBEDDING_MODEL=Qwen/Qwen3-Embedding-4B
GRAPHRAG_EMBEDDING_API_BASE=http://localhost:8000/v1

# 默认书籍配置（可修改）
DEFAULT_BOOK_ID=default-book
DEFAULT_BOOK_TITLE=默认小说
DEFAULT_BOOK_PATH=default-book.txt
```

### 上传小说

将你的小说文本文件（TXT 格式）放到项目根目录，例如 `my-novel.txt`。

### 构建索引

```bash
python scripts/build_index.py
```

### 启动服务

```bash
python scripts/run_api.py
```

打开浏览器访问 `http://127.0.0.1:8000` 查看前端界面。

### 运行评测

准备评测用例文件 `eval_cases.jsonl`，然后运行：

```bash
python scripts/run_eval.py
```

评测结果会写入 `data/runtime/eval_report.json`，工作台里的 Evaluation Dashboard 会自动读取。

## 项目结构

```
fanren-novel-system/
├── novel_system/
│   ├── graphrag_app/        # GraphRAG 应用层（核心）
│   │   ├── workspace.py     # 工作区生命周期管理
│   │   ├── input_builder.py # TXT -> GraphRAG input/*.txt
│   │   ├── settings_builder.py  # 生成 settings.yaml
│   │   ├── prompt_manager.py    # 小说领域 Prompt 管理
│   │   ├── index_runner.py      # CLI subprocess 索引执行
│   │   ├── table_loader.py      # Parquet 表加载与别名映射
│   │   ├── table_validator.py   # 输出表完整性校验
│   │   ├── query_router.py      # local/global/drift/basic 路由
│   │   ├── query_engine.py      # GraphRAG Python API 查询入口
│   │   ├── answer_adapter.py    # GraphRAG 结果 -> AskResponse
│   │   ├── graph_projector.py   # entities/relationships -> 前端图谱
│   │   ├── timeline_projector.py # covariates/text_units -> 时间线
│   │   └── debug_dump.py        # 调试输出
│   ├── services/            # 业务服务层
│   │   ├── indexing.py      # GraphRAG 索引编排
│   │   ├── qa.py            # GraphRAG 查询入口
│   │   ├── continuation.py  # 续写（迁移中降级）
│   │   └── stats.py         # 统计
│   ├── legacy/              # 旧 RAG 模块（参考）
│   ├── api.py               # FastAPI 路由
│   ├── config.py            # 配置管理
│   ├── models.py            # 数据模型
│   └── validator.py         # 验证层
├── static/                  # 前端
├── templates/               # HTML 模板
├── tests/graphrag_app/      # GraphRAG 测试
└── data/books/{book_id}/graphrag/
    ├── input/               # 章节 TXT
    ├── settings.yaml        # GraphRAG 配置
    ├── prompts/             # 小说领域 Prompt
    ├── output/              # Parquet 表
    └── derived/             # 前端视图（graph_view.json, timeline_view.json）
```

## API 文档

启动服务后访问：
- Swagger UI: `http://127.0.0.1:8000/docs`
- ReDoc: `http://127.0.0.1:8000/redoc`

### 主要端点

#### `POST /api/books/{book_id}/ask`
GraphRAG 智能问答

```json
{
  "user_query": "主角是怎么得到关键道具的？",
  "search_mode": "auto",
  "conversation_history": [],
  "debug": false
}
```

search_mode 选项: `auto` | `local` | `global` | `drift` | `basic`

#### `POST /api/books/{book_id}/continue`
情节续写（GraphRAG 迁移中，当前返回降级提示）

```json
{
  "user_query": "主角进入门派后的第一次历练"
}
```

#### `POST /api/books`
上传新书

#### `POST /api/books/{book_id}/index`
为书籍构建索引

#### `GET /api/books`
获取书籍列表

#### `GET /api/books/{book_id}/graph`
获取人物关系图谱

#### `GET /api/books/{book_id}/timeline`
获取情节时间线

#### `GET/PUT /api/books/{book_id}/canon`
获取/更新世界观设定

## 查询重写

系统会自动对用户查询进行优化：

1. **别名扩展**: 支持人物别名映射，如"二愣子"自动扩展为包含主角真名
2. **指代消解**: 自动识别"那个瓶子"、"这个功法"等指代
3. **上下文提取**: 从对话历史中提取关键人物和实体
4. **章节引用**: 提取章节号并扩展到查询中

## 追踪功能

系统支持完整的请求追踪，用于调试和分析：

```bash
# 启用追踪返回
curl -X POST "http://localhost:8000/api/books/{book_id}/ask" \
  -H "Content-Type: application/json" \
  -d '{"user_query": "问题内容", "debug": true}'
```

返回的响应中会包含 `trace` 字段，包含：
- `query_rewrite`: 查询重写详情（原文、重写后、扩展词）
- `retrieval`: 检索详情（目标、命中数、Top10 命中）
- `evidence_spans`: 证据片段详情
- `total_duration_ms`: 总耗时

环境变量控制：
- `TRACE_ENABLED=true` - 启用追踪日志写入文件
- `TRACE_LOG_LEVEL=INFO` - 日志级别

## 验证层

系统内置多层验证机制：

1. **Evidence Gate**: 检测检索结果是否足以回答问题，不足时返回拒答
2. **Answer Validator**: 评估回答与证据的一致性
3. **Continuation Validator**: 检查续写内容的人物一致性和世界观合规性
4. **GraphRAG Table Validator**: 验证索引输出表完整性

## 人物关系图谱

系统自动提取人物并构建关系网络：

- 基于章节内容的自动命名实体识别
- 基于事件的参与者关系推断
- 支持人物别名映射
- 知识图谱种子修正
- 力导向图可视化，支持节点拖拽和缩放

## 开发指南

### 添加小说特定规则（可选）

在 `novel_system/novel_heuristics.py` 中添加小说特定的规则：

```python
def heuristic_answer(query: str, scope: Scope, memory: MemoryState) -> str | None:
    q = query.strip()
    # 添加特定问题的快速响应
    if "某个特定问题" in q:
        return "根据第X章的答案..."
    return None

def heuristic_continuation(query: str) -> str | None:
    # 添加续写限制规则
    if "超出设定" in query:
        return "此要求超出当前设定范围，无法续写。"
    return None
```

### 扩展检索目标

在 `novel_system/models.py` 中定义新的 `RetrievalTarget`：

```python
RetrievalTarget = Literal[
    "chapter_chunks",
    "character_card",
    "your_new_target",
]
```

## 技术栈

- **后端**: FastAPI
- **前端**: HTML5 Canvas + Vanilla JavaScript
- **知识图谱**: Microsoft GraphRAG v3.0.9
- **检索模式**: Local / Global / DRIFT / Basic Search
- **LLM**: MiniMax via LiteLLM
- **Embedding**: Qwen3-Embedding-4B (local server)
- **数据存储**: Parquet + 本地文件系统

## 更新日志

### 2026-05-22 - 项目结构优化与重构

**优化调整：**
- **代码精简与重构**:
  - 将 `novel_system/artifacts/` 目录下的所有构建逻辑（`SceneSegmentBuilder`, `CharacterRegistryBuilder` 等）与 `novel_system/index_pipeline.py` 整合至 `novel_system/indexing.py`。
  - 提取公共的文本处理逻辑（如句子切分、事件语句评分、预编译正则表达式等）至 `novel_system/utils/text_utils.py`，实现模块解耦。
  - 清理多余的临时文件，统一测试与运行入口。

### 2026-04-14 - 场景感知检索重构

**新模块：**
- **Artifact Pipeline (`novel_system/artifacts/`)**: 稳定的中间产物构建器
  - `SceneSegmentBuilder`: 基于地点转换进行场景分割，保留角色和事件元数据
  - `CharacterRegistryBuilder`: 角色注册表，支持别名合并、活跃章节范围追踪
  - `targets.py`: 从场景和角色注册表构建 `chapter_chunks`、`event_timeline`、`character_card`
- **Search Package (`novel_system/search/`)**: 多目标检索编排
  - `SearchOrchestrator`: 搜索编排器，支持精确别名匹配和稀疏文本匹配
  - `profiles.py`: 目标配置（文本字段、ID字段、别名字段）
  - `base.py`: 基础类型定义
- **Index Pipeline (`novel_system/index_pipeline.py`)**: 公共索引管道入口

**核心改进：**
- **检索意图驱动**: `PlannerOutput` 新增 `retrieval_intent` 字段
  - `alias_resolution`: 角色查询优先精确别名匹配
  - `causal_chain`: 因果链查询优先事件时间线
  - `scene_evidence`: 默认场景证据检索
- **角色别名解析**: 支持"二愣子"→"韩立"等别名自动合并
- **章节范围过滤**: 检索结果自动按章节范围过滤，支持角色卡 `active_range`

**测试：**
- 新增 17 个测试用例，覆盖场景分割、角色注册表、目标构建器、搜索编排器
- 总计 89 个测试通过

### 2026-04-14 - 实体一致性检查 & Embedding API 修复

**新功能：**
- **实体抽取模块 (EntityExtractor)**: 从文本中抽取实体属性（性格、外貌、体型、颜色、修为等级）
  - 支持预编译正则模式，优化性能
  - 词库 + 正则上下文约束的双重匹配
  - 支持否定词检测，避免误匹配
  - 支持性格对立词检测（如"谨慎"与"莽撞"）
  - 支持修为等级跳跃检测
- **实体一致性检查**: 验证答案/续写与证据之间的实体属性是否一致
  - 集成到 AnswerValidator 和 ContinuationValidator
  - 自动检测人物性格、外貌、修为等级矛盾

**修复：**
- 修复 MiniMax embedding API 调用格式：
  - 使用 `texts` 字段替代 `input`
  - 添加必需的 `type` 参数（`query`/`document`）
  - 正确处理 `vectors` 响应字段

**改进：**
- validator.py 扩展 271 行，增强验证能力
- 新增 entity_extractor.py 模块
- 新增 test_entity_extractor.py 测试

### 2026-04-13 - 验证层与追踪系统

**新功能：**
- **追踪系统 (Tracing)**: 完整的请求追踪能力，记录查询重写、检索、验证等各阶段详情
  - 通过 `debug=true` 参数启用，返回完整追踪数据
  - 支持环境变量配置：`TRACE_ENABLED`、`TRACE_LOG_LEVEL`
- **验证层 (Validation Layer)**: 多层次的内容验证机制
  - **Evidence Gate**: 证据门控，检测检索结果是否足以回答问题
  - **Answer Validator**: 答案验证器，评估回答质量
  - **Continuation Validator**: 续写验证器，检查人物一致性、世界观合规性
  - **Spoiler Guard**: 剧透防护，自动检测并处理超出范围的剧透内容
- **语义评分器**: 新增语义相关性评分模块

**改进：**
- 类型注解兼容性优化（使用 `Optional[X]` 替代 `X | None`）
- 移除 dataclass slots 以提升兼容性

## 许可证

MIT License

## 贡献

欢迎提交 Issue 和 Pull Request！
