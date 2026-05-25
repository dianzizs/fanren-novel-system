# NovelQA System — GraphRAG 长篇小说问答与分析系统

基于 Microsoft GraphRAG v3.0.9 构建的中文长篇小说全书分析系统。通过自动解析、实体与关系抽取、社区发现构建全书维度的多模式检索（Local / Global / DRIFT / Basic）和深度分析能力。

## 1. 项目简介

- 这是一个面向长篇小说 / 全书内容的智能问答与深度分析系统。系统通过从全书文本中提取实体、关系和事件，帮助用户进行角色追踪、势力分析以及故事脉络整理。
- 项目当前已全面迁移至以 **Microsoft GraphRAG** (v3.0.9) 为核心的知识图谱问答与分析架构，舍弃了旧有的混合检索。
- 旧版的 RAG 混合检索链路（包括 TF-IDF、FAISS 向量检索、剧透判定等）已经被彻底物理清理，目前仅保留部分测试兼容配置，不再作为推荐的问答主路径。

## 2. 当前项目状态

| 模块 | 状态 | 说明 |
|---|---|---|
| FastAPI 服务 | 可用 | 服务启动入口，提供全量 REST API 并托载 Web Dashboard，端口为 8000。 |
| GraphRAG 索引 | 可用 | 依赖 GraphRAG CLI 异步构建。可以为上传的小说自动准备 Workspace、生成 settings.yaml 并构建索引。 |
| GraphRAG 查询 | 可用 | 主问答路径。基于 GraphRAG Python API，支持 Local / Global / DRIFT / Basic 四种检索模式和 Auto 智能路由。 |
| 本地 embedding | 需要配置 | 依赖本地运行的 OpenAI-compatible Embedding Server（推荐使用 GPU 或 CPU 加速的 OpenVINO 服务）。 |
| MiniMax / LLM | 需要 API Key | 依赖外接大语言模型（默认 MiniMax，支持备用 Mimo/Anthropic API）提供文本实体抽取和问答生成能力。 |
| 旧版 RAG | legacy / 已清理 | 旧版 FAISS 向量存储、混合检索和 `retrieval.py` 核心逻辑已被彻底物理删除，不再作为主路径。 |
| 测试 | 可用 | 拥有 181 个 pytest 测试用例，通过率 100%。 |

## 3. 项目结构

```text
fanren-novel-system/
  novel_system/
    api.py                  # FastAPI 路由，已适配 GraphRAG 异步查询模式
    config.py               # 配置管理，加载环境变量并自动构建配置实例
    graphrag_app/           # GraphRAG 适配层（核心新增），封装 Workspace、QueryEngine 等
      workspace.py          # 负责每本小说的 Workspace 初始化与环境准备
      input_builder.py      # 负责将小说原始 TXT 转换为 GraphRAG 标准输入格式
      settings_builder.py   # 自动渲染 settings.yaml 配置文件
      index_runner.py       # 封装 subprocess 执行 GraphRAG CLI 索引命令
      query_engine.py       # 封装 GraphRAG Python API，统一四种检索方式
      query_router.py       # 智能路由用户问题至最匹配的检索模式
      table_loader.py       # 负责读取 GraphRAG 生成的 Parquet 数据表
      graph_projector.py    # 提取实体和关系生成前端图谱 JSON
      timeline_projector.py # 提取事件时间线数据
    services/               # 业务服务层 Mixin
      indexing.py           # 构建流水线编排
      qa.py                 # GraphRAG 多模式问答接口
      continuation.py       # 情节续写服务（当前处于降级预览阶段）
    indexing/               # 重构后的索引子包，承载小说章节分拆、场景提取等基础解析
    llm.py                  # 大模型调用客户端，支持 MiniMax 与 Mimo
    models.py               # 数据契约定义（Pydantic v2 模型）
    validator.py            # 回答一致性与合规性验证层
  templates/                # 页面模板（Jinja2）
  static/                   # 静态资源（CSS/JS）
    js/                     # 前端 ES Modules 模块
    app.js                  # 遗留死代码（仅用于测试回归，已废弃）
  tests/                    # pytest 测试套件
    graphrag_app/           # GraphRAG 适配层专项测试
  start_server.py           # 统一后端服务启动入口
  requirements.txt          # Python 依赖清单
  .env.example              # 环境变量模板
```

## 4. 快速开始与启动指南

### 4.1 环境准备

1. **安装 Python 运行时**：建议使用 Python 3.11 或 3.12。
2. **激活 Conda 环境**：
   ```bash
   conda activate chaishu
   ```
3. **安装依赖**：
   ```bash
   pip install -r requirements.txt
   ```
4. **安装 Microsoft GraphRAG**：本项目使用 `graphrag` 库进行索引与检索，需要以可编辑模式（editable install）安装本地的 `graphrag` 包（指定版本 v3.0.9）：
   ```bash
   pip install -e D:\pythonProject\graphrag\packages\graphrag
   ```

### 4.2 配置环境变量

复制 `.env.example` 并创建 `.env`：
```bash
cp .env.example .env
```
根据你的环境修改 `.env` 中的核心配置：
- `MINIMAX_API_KEY`: 填入你的 MiniMax 大模型 API Key。
- `EMBEDDING_PROVIDER`: 默认为 `local_openvino`，依赖本地的 Embedding 向量服务。
- `LOCAL_EMBEDDING_MODEL`: 默认为 `BAAI/bge-small-zh-v1.5`。
- `GRAPHRAG_EMBEDDING_API_BASE`: 本地 Embedding 服务接口地址（通常为 `http://localhost:8000/v1`）。

> [!IMPORTANT]
> 项目非常依赖本地 Embedding Server 和 MiniMax API。运行索引与问答前，请确保 Embedding Server 已在后台正常运行。

### 4.3 启动 API 服务

```bash
conda run -n chaishu python start_server.py
```
服务启动后，可以访问以下页面：
- **Web 可视化控制台 (Dashboard)**: `http://localhost:8000`
- **FastAPI 交互式 API 文档 (Swagger)**: `http://localhost:8000/docs`

### 4.4 书籍导入与索引构建

1. 访问 Web 页面（Dashboard）或者使用 REST API 注册一本书（例如上传 `.txt` 小说）。
2. 在控制台点击 **"构建索引"**，或者发送 POST 请求：
   ```bash
   curl -X POST "http://localhost:8000/api/books/{book_id}/start-index"
   ```
3. 构建索引将通过子进程异步调用 `graphrag index`，可能耗时较长（需要进行大范围实体抽取与关系提炼）。可以通过 `GET /api/books/{book_id}/status` 监控构建进度。
4. 索引构建完成后，系统将自动生成对应的派生图谱和时间线，供前端渲染。

### 4.5 运行测试

项目自带完整的回归测试用例，在修改代码或配置文件后，请务必运行测试以确保系统没有引入 Regression：
```bash
conda run -n chaishu python -m pytest
```

## 5. 常见排错机制

### 5.1 导入新书后在 Web 页面“点击导入”按钮没有反应
- **原因**：浏览器缓存了旧的前端 JS 文件。
- **解决方法**：请在浏览器中执行**强刷缓存**（Windows 快捷键 `Ctrl + F5`，或在开发者工具中开启 "Disable Cache"），然后再试。

### 5.2 索引构建任务报错或卡在 0% 不动
- **原因**：通常是由于本地 Embedding 服务未启动，或大模型 API 调用由于无效 Key、额度不足、网络超时而报错。
- **排错步骤**：
  1. 检查本地 `http://localhost:8000/v1` (或你配置的 Embedding 路径) 是否可访问，并且可以通过 `/v1/embeddings` 生成向量。
  2. 查看后台控制台的日志，或者是 `data/books/{book_id}/graphrag/` 路径下的 `index_runner.py` 报错日志。
  3. 检查大模型 API 额度，确认 `.env` 中填写的 `MINIMAX_API_KEY` 正确无误。

### 5.3 提示 `ModuleNotFoundError: No module named 'graphrag'`
- **原因**：未在 Conda 环境中正确安装 Microsoft GraphRAG。
- **解决方法**：执行可编辑模式安装 `pip install -e D:\pythonProject\graphrag\packages\graphrag`，并确认所用 Python 环境与启动服务时的一致。
