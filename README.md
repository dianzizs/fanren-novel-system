# Fanren Novel System

一个基于 FastAPI 构建的中文小说问答系统，专为《凡人修仙传》等长篇武侠/仙侠小说设计。系统提供智能问答、情节续写、人物关系图谱可视化等功能。

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

DEFAULT_BOOK_ID=fanren-1-500
DEFAULT_BOOK_TITLE=凡人修仙传（1-500章）
DEFAULT_BOOK_PATH=./凡人修仙传(1-500章).txt
```

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

```bash
python scripts/run_eval.py
```

评测结果会写入 `data/runtime/eval_report.json`，工作台里的 Evaluation Dashboard 会自动读取。

## 项目结构

```
fanren-novel-system/
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
│   └── fanren_heuristics.py  # 小说特定规则
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
  "user_query": "韩立是怎么得到小瓶的？",
  "scope": {"chapters": [1, 50]},
  "conversation_history": [],
  "top_k": 6
}
```

#### `POST /api/continue`
情节续写

```json
{
  "user_query": "韩立进入七玄门后的第一次历练",
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

1. **别名扩展**: "二愣子" → "韩立 二愣子"
2. **指代消解**: "那个瓶子" → "神秘小瓶"
3. **上下文提取**: 从对话历史中提取关键人物和实体
4. **章节引用**: 提取章节号并扩展到查询中

## 人物关系图谱

系统自动提取人物并构建关系网络：

- 基于章节内容的自动命名实体识别
- 基于事件的参与者关系推断
- 支持人物别名映射
- 知识图谱种子修正
- 力导向图可视化，支持节点拖拽和缩放

## 开发指南

### 添加新的小说适配

在 `novel_system/fanren_heuristics.py` 中添加小说特定的规则：

```python
# 人物别名映射
ALIAS_EXPANSIONS = {
    "韩立": ["二愣子", "韩师弟"],
    # ...
}

# 知识图谱种子
GRAPH_CANON_SEEDS = {
    "韩立": "主角，性格沉稳谨慎",
    # ...
}
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

## 许可证

MIT License

## 贡献

欢迎提交 Issue 和 Pull Request！
