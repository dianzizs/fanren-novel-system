# 小王一号 - 配置文档

## 环境变量

### Embedding 相关

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `EMBEDDING_PROVIDER` | `local_openvino` | Embedding 提供者类型 |
| `LOCAL_EMBEDDING_MODEL` | `BAAI/bge-small-zh-v1.5` | 本地 embedding 模型名称 |
| `LOCAL_EMBEDDING_DEVICE` | `CPU` | 推理设备（CPU/GPU） |
| `LOCAL_EMBEDDING_FALLBACK_DEVICE` | `CPU` | 回退设备 |
| `LOCAL_EMBEDDING_BATCH_SIZE` | `32` | 批处理大小 |
| `LOCAL_EMBEDDING_NORMALIZE` | `true` | 是否归一化向量 |
| `LOCAL_EMBEDDING_CACHE_DIR` | `~/.cache/huggingface` | 模型缓存目录 |

### 向量检索相关

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `VECTOR_SEARCH_ENABLED` | `true` | 是否启用向量检索 |
| `FAISS_USE_GPU` | `false` | FAISS 是否使用 GPU |
| `FAISS_METRIC` | `ip` | 距离度量（ip/l2） |

### 追踪相关

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `TRACE_ENABLED` | `false` | 是否启用追踪日志 |
| `TRACE_LOG_LEVEL` | `INFO` | 日志级别 |

## 配置类 (AppConfig)

```python
from novel_system.config import AppConfig

config = AppConfig(
    # 路径配置
    root_dir=Path("."),
    data_dir=Path("data"),
    runtime_dir=Path("data/runtime"),
    books_dir=Path("data/books"),

    # 默认书籍配置
    default_book_id="default-book",
    default_book_title="Default",
    default_book_path=Path("default.txt"),

    # MiniMax API 配置
    minimax_api_key="",
    minimax_base_url="https://api.minimax.chat/v1",
    minimax_chat_model="MiniMax-m2.7-HighSpeed",

    # Embedding 配置
    embedding_provider="local_openvino",
    local_embedding_model="BAAI/bge-small-zh-v1.5",
    local_embedding_device="CPU",
    local_embedding_fallback_device="CPU",
    local_embedding_batch_size=32,
    local_embedding_normalize=True,
    local_embedding_cache_dir=Path("cache"),

    # 追踪配置
    trace_enabled=False,
    trace_log_level="INFO",
)
```

## Embedding Provider 选择

### local_openvino

适用于 Intel CPU/GPU，使用 OpenVINO 优化推理。

**优点：**
- Intel 硬件上性能优秀
- 支持 CPU 和 GPU

**缺点：**
- 需要安装 OpenVINO
- 首次运行需要编译模型

### local_cuda

适用于 NVIDIA GPU，使用 CUDA 加速。

**优点：**
- NVIDIA GPU 上性能优秀
- 部署简单

**缺点：**
- 需要 NVIDIA GPU 和 CUDA

## 向量检索配置建议

### 生产环境

```bash
# 启用向量检索
export EMBEDDING_PROVIDER=local_openvino
export LOCAL_EMBEDDING_DEVICE=GPU
export LOCAL_EMBEDDING_FALLBACK_DEVICE=CPU
export FAISS_USE_GPU=false  # 通常 CPU 足够
```

### 开发环境

```bash
# 简化配置
export EMBEDDING_PROVIDER=local_openvino
export LOCAL_EMBEDDING_DEVICE=CPU
```

### 测试环境

```bash
# 禁用向量检索（仅 TF-IDF）
# 不设置 EMBEDDING_PROVIDER 或使用 MockEmbeddingProvider
```

## 索引文件结构

```
data/books/<book_id>/
├── manifest.json           # 书籍元数据
├── chapters.json           # 章节内容
├── chapter_chunks.json     # 章节分块
├── chapter_chunks.pkl      # TF-IDF 索引
├── chapter_summaries.json  # 章节摘要
├── event_timeline.json     # 事件时间线
├── character_card.json     # 角色卡片
├── relationship_graph.json # 关系图
├── world_rule.json         # 世界规则
├── canon_memory.json       # 正典记忆
├── recent_plot.json        # 近期剧情
├── style_samples.json      # 风格样本
└── vectors/                # 向量索引目录
    ├── chapter_chunks/
    │   ├── index.faiss
    │   └── metadata.json
    ├── chapter_summaries/
    │   ├── index.faiss
    │   └── metadata.json
    └── .../
```

## 混合检索原理

混合检索结合了稀疏检索（TF-IDF）和稠密检索（向量）的优势：

1. **TF-IDF（稀疏检索）**：基于关键词匹配，对精确词匹配效果好
2. **向量检索（稠密检索）**：基于语义相似度，对同义词、近义词效果好

**结果合并策略**：
- 相同文档取最高分
- 按分数降序排列

**降级策略**：
- 无向量索引 → 仅 TF-IDF
- embedding 计算失败 → 仅 TF-IDF
- 向量搜索异常 → 仅 TF-IDF
