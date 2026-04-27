# 小王一号 - 模块文档

## 核心模块

### novel_system/indexing.py

索引构建与管理模块。

**主要功能：**
- `BookIndexRepository`: 书籍索引仓库，负责索引的构建、加载和管理
- `LoadedBookIndex`: 加载的书籍索引数据结构，包含：
  - `manifest`: 书籍元数据
  - `chapters`: 章节列表
  - `corpora`: 各种文档语料库
  - `vectorizers`: TF-IDF 向量化器
  - `matrices`: TF-IDF 矩阵
  - `vector_stores`: 向量存储（用于稠密检索）

**向量索引集成：**
- `BookIndexRepository.__init__(config, embedding_provider=None)`: 接受可选的 embedding_provider
- `build_from_txt()`: 构建索引时同时创建向量索引（如果提供了 embedding_provider）
- `load()`: 加载索引时自动加载向量索引
- `_build_faiss_index()`: 构建 FAISS 向量索引的内部方法

### novel_system/search/orchestrator.py

搜索编排模块，负责多目标检索。

**主要功能：**
- `SearchOrchestrator`: 搜索编排器
- `Hit`: 搜索命中结果数据结构

**检索方法：**
- `retrieve()`: 主检索方法，支持 TF-IDF 和向量混合检索
  - 参数：`query_embedding` - 可选的查询向量，用于稠密检索
- `_tfidf_search()`: TF-IDF 稀疏检索
- `_dense_search()`: 向量稠密检索
- `_dedupe_candidates()`: 结果去重，相同文档取最高分

### novel_system/retrieval.py

检索兼容层，提供向后兼容的检索接口。

**主要功能：**
- `HybridRetriever`: 混合检索器，委托给 `SearchOrchestrator`
- `RetrievalHit`: 检索命中结果

**参数：**
- `query_embedding`: 可选的查询向量，传递给 `SearchOrchestrator.retrieve()`

### novel_system/service.py

核心服务模块。

**向量检索集成：**
- `NovelSystemService` 初始化时创建 `embedding_provider`
- `_compute_query_embedding()`: 计算查询文本的 embedding 向量
- `_retrieve_with_rewrite()`: 使用 embedding 进行混合检索

### novel_system/vector_store/

向量存储模块。

**主要组件：**
- `BaseVectorStore`: 向量存储抽象基类
- `FAISSVectorStore`: FAISS 向量存储实现
  - 支持内积（IP）和 L2 距离
  - 支持 CPU 和 GPU
  - 支持磁盘持久化

**文件结构：**
```
<book_dir>/vectors/<corpus_name>/
├── index.faiss      # FAISS 索引文件
└── metadata.json    # 元数据（ID 映射、文档等）
```

### novel_system/embedding/

Embedding 模块。

**主要组件：**
- `EmbeddingProvider`: Embedding 提供者抽象基类
- `LocalOpenVINOEmbeddingProvider`: 本地 OpenVINO 实现
- `LocalCudaEmbeddingProvider`: 本地 CUDA 实现

## 检索流程

### 混合检索流程

```
用户查询
    ↓
service.py: _compute_query_embedding()
    ↓
retrieval.py: HybridRetriever.retrieve(query_embedding=...)
    ↓
orchestrator.py: SearchOrchestrator.retrieve()
    ├── _dense_search() → 向量检索结果
    └── _tfidf_search() → TF-IDF 检索结果
    ↓
_dedupe_candidates() → 合并去重
    ↓
返回最终结果
```

### 降级策略

1. **无 embedding_provider**: 不计算 query_embedding，仅使用 TF-IDF
2. **embedding 计算失败**: 返回 None，降级到纯 TF-IDF
3. **无向量索引**: vector_stores 为空，仅使用 TF-IDF
4. **向量搜索异常**: `_dense_search()` 返回空列表
