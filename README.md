# NovelQA System

一个基于 FastAPI 构建的通用中文小说问答系统，支持任意长篇小说的智能分析。系统提供智能问答、情节续写、人物关系图谱可视化等功能。

## 功能特性

### 核心功能
- **智能问答**: 基于章节内容进行语义检索，提供准确的问题回答
- **情节续写**: 基于原著风格和人物设定进行续写
- **人物卡片**: 自动提取人物信息，生成详细人物卡
- **时间线**: 梳理情节发展，生成时间线视图
- **关系图谱**: 可视化人物关系网络，支持力导向图交互
- **摘要生成**: 自动生成章节摘要和情节概括

### 技术特性
- **混合检索**: 结合 TF-IDF 语义搜索与规则匹配
- **查询重写**: 自动扩展别名、消解指代、提取上下文
- **范围限制**: 支持章节范围查询，防止剧透
- **风格保持**: 保持原著语言风格进行续写和回答
- **评测系统**: 集成评测脚本与可视化 Dashboard

## 快速开始

### 环境要求
- Python 3.9+
- pip

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
novelqa-system/
├── novel_system/          # 核心模块
│   ├── __init__.py
│   ├── api.py            # FastAPI 应用和路由
│   ├── config.py         # 配置管理
│   ├── indexing.py       # 索引构建和加载
│   ├── llm.py            # LLM 客户端封装
│   ├── models.py         # 数据模型定义
│   ├── planner.py        # 查询规划和重写
│   ├── retrieval.py      # 混合检索引擎
│   ├── service.py        # 核心业务逻辑
│   ├── tracing.py        # 追踪日志基础设施
│   ├── validator.py      # 验证层（证据门控、答案验证、剧透防护）
│   ├── semantic_scorer.py # 语义相关性评分
│   └── novel_heuristics.py  # 小说特定规则（可选）
├── scripts/              # 脚本工具
│   ├── build_index.py    # 索引构建脚本
│   ├── run_api.py        # API 启动脚本
│   └── run_eval.py       # 评估脚本
├── static/               # 前端静态文件
│   ├── app.js           # 前端交互逻辑
│   └── styles.css       # 样式表
├── templates/            # HTML 模板
│   └── dashboard.html    # 主页面
├── tests/               # 测试文件
└── data/                # 数据目录
    ├── books/          # 小说文本文件
    └── runtime/        # 运行时数据（索引、缓存）
```

## API 文档

启动服务后访问：
- Swagger UI: `http://127.0.0.1:8000/docs`
- ReDoc: `http://127.0.0.1:8000/redoc`

### 主要端点

#### `POST /api/ask`
智能问答

```json
{
  "user_query": "主角是怎么得到关键道具的？",
  "scope": {"chapters": [1, 50]},
  "conversation_history": [],
  "top_k": 6
}
```

#### `POST /api/continue`
情节续写

```json
{
  "user_query": "主角进入门派后的第一次历练",
  "scope": {"chapters": [1, 100]},
  "desired_length": [500, 1000]
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
4. **Spoiler Guard**: 自动检测并处理超出查询范围的剧透内容

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
- **检索**: TF-IDF 语义检索
- **LLM**: MiniMax API
- **数据存储**: 本地文件系统

## 更新日志

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
