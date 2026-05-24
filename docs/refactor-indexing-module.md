# indexing.py 拆分重构方案

## 背景

`novel_system/indexing.py` 当前约 1700 行，包含一个巨型类 `BookIndexRepository` 和三个辅助类（`CharacterRegistryBuilder`、`SceneSegmentBuilder`、`FilterThresholds`），混合了 5 种不同职责。本方案将其拆分为语义清晰的子模块，保持外部接口不变。

---

## 当前文件结构分析

| 行号范围 | 内容 | 归属模块 |
|----------|------|----------|
| 1-120 | 常量（正则、停用词、姓氏表、规则模式） | `constants.py` |
| 122-136 | `LoadedBookIndex` dataclass | `models.py` |
| 138-254 | `BookIndexRepository.__init__` + manifest 管理方法 | `repository.py` |
| 253-346 | LLM 提取：`_extract_structured_from_llm` | `llm_extraction.py` |
| 348-401 | LLM 预热：`prewarm_llm_extractions` | `llm_extraction.py` |
| 402-499 | `build_from_txt`（编排入口） | `repository.py` |
| 501-577 | `load` + `_book_dir` | `repository.py` |
| 579-636 | 文本解析：`_parse_chapters`、`_build_chunks` | `parser.py` |
| 637-1180 | Artifact 构建：summaries、events、cards、registry、relationships、world_rules、canon_memory、style_samples、recent_plot | `artifact_builders.py` |
| 1182-1287 | 向量化：TF-IDF payload、FAISS 构建与保存 | `vector_indexing.py` |
| 1288-1297 | 文本工具：`_clean_line`、`_split_sentences`、`_score_event_sentence` | `parser.py` |
| 1299-1383 | NER + LLM 名字过滤：`_filter_names_with_llm`、`_extract_person_names` | `llm_extraction.py` |
| 1385-1391 | `scope_filter` 独立函数 | `models.py` |
| 1393-1665 | `FilterThresholds`、`CharacterRegistryBuilder`、`SceneSegmentBuilder` | `scene.py` |
| 1667-end | `build_chapter_chunks` 独立函数 | `scene.py` |

---

## 目标结构

```
novel_system/
├── indexing/
│   ├── __init__.py              # 重新导出公共接口
│   ├── constants.py             # 正则、停用词、姓氏表等常量
│   ├── models.py                # LoadedBookIndex, scope_filter
│   ├── repository.py            # BookIndexRepository（瘦身后）
│   ├── parser.py                # 章节解析、分句、清洗
│   ├── artifact_builders.py     # 所有 _build_* artifact 方法
│   ├── llm_extraction.py        # LLM 结构化提取 + 名字过滤 + NER
│   ├── vector_indexing.py       # TF-IDF + FAISS 构建/加载
│   └── scene.py                 # SceneSegmentBuilder, CharacterRegistryBuilder, FilterThresholds, build_chapter_chunks
```

---

## 各模块详细内容

### 1. `constants.py`（~80 行）

从原文件提取所有模块级常量：

```python
# 搬入内容：
CHAPTER_RE
SENTENCE_RE
COMMON_SURNAMES
PERSON_RE
TITLE_PERSON_RE
ORG_RE
STOP_NAMES
BAD_NAME_ENDINGS
RULE_PATTERNS
LOCATION_SHIFT_RE
```

### 2. `models.py`（~30 行）

```python
# 搬入内容：
@dataclass LoadedBookIndex
def scope_filter(...)
```

依赖：`TfidfVectorizer`（类型注解）、`BaseVectorStore`（TYPE_CHECKING）

### 3. `repository.py`（~300 行）

保留 `BookIndexRepository` 类的骨架：

```python
# 保留方法：
__init__
list_books
remove_book
update_book_manifest
ensure_book_manifest
read_artifact
load              # 加载索引（调用 vector_indexing 的加载逻辑）
build_from_txt    # 编排入口（调用各子模块）
_book_dir
llm (property)
```

`build_from_txt` 改为调用子模块函数：

```python
from .parser import parse_chapters, build_chunks, clean_line
from .artifact_builders import (
    build_chapter_summaries, build_event_timeline,
    build_character_cards, build_character_registry,
    build_relationships, build_world_rules,
    build_canon_memory, build_style_samples, build_recent_plot_docs,
)
from .llm_extraction import prewarm_llm_extractions, extract_person_names
from .vector_indexing import build_vector_payload, build_vector_indexes, build_faiss_index
```

### 4. `parser.py`（~80 行）

纯函数，无类依赖：

```python
# 搬入内容：
def parse_chapters(raw_text: str) -> list[dict]     # 原 _parse_chapters
def build_chunks(chapters, chunk_size=420, overlap=80) -> list[dict]  # 原 _build_chunks
def clean_line(line: str) -> str                     # 原 _clean_line
def split_sentences(text: str) -> list[str]          # 委托 utils.text_utils
def score_event_sentence(sentence: str) -> float     # 委托 utils.text_utils
```

依赖：`constants.py`（`CHAPTER_RE`）、`utils.text_utils`

### 5. `artifact_builders.py`（~550 行）

所有 artifact 构建逻辑，改为接收参数而非 `self`：

```python
# 函数签名示例：
def build_chapter_summaries(chapters, split_sentences_fn) -> list[dict]
def build_event_timeline(chapters, chapter_summaries, llm_extractions, split_sentences_fn, score_fn, extract_names_fn) -> list[dict]
def build_character_cards(chapters, book_id, config, llm_extractions, token_callback) -> list[dict]
def build_character_registry(chapters, character_cards, book_id, config, llm_extractions, extract_names_fn, filter_names_fn, token_callback) -> list[dict]
def build_relationships(chapters, character_cards, llm_extractions, config, extract_names_fn) -> list[dict]
def build_world_rules(chapters, split_sentences_fn) -> list[dict]
def build_canon_memory(chapter_summaries, events) -> list[dict]
def build_style_samples(chapters) -> list[dict]
def build_recent_plot_docs(chapters, chapter_summaries, split_sentences_fn) -> list[dict]
```

依赖：`constants.py`（`RULE_PATTERNS`）、`graph_name_policy`

### 6. `llm_extraction.py`（~280 行）

```python
# 搬入内容：
def extract_structured_from_llm(llm_client, chunk_text, book_dir, book_id, token_callback) -> Optional[ChapterChunkExtraction]
def prewarm_llm_extractions(llm_client, chapters, book_id, book_dir, token_callback) -> dict[int, list]
def filter_names_with_llm(config, names, batch_size=50, token_callback=None) -> set[str]
def extract_person_names(text: str) -> list[str]     # 原 _extract_person_names
def build_extraction_chunks(chapter_text, chunk_size=1800, overlap=250) -> list[str]
```

依赖：`constants.py`（`PERSON_RE`、`TITLE_PERSON_RE`、`STOP_NAMES`、`BAD_NAME_ENDINGS`）、`extraction_models`、`llm.MiniMaxClient`

### 7. `vector_indexing.py`（~120 行）

```python
# 搬入内容：
def tokenize_chinese(text: str) -> list[str]
def build_vector_payload(docs: list[dict]) -> dict
def build_faiss_index(docs, embedding_provider) -> Optional[FAISSVectorStore]
def build_vector_indexes(book_id, corpora, config, embedding_provider) -> bool
def load_vector_stores(book_id, config) -> dict[str, BaseVectorStore]
```

依赖：`jieba`、`numpy`、`TfidfVectorizer`、`FAISSVectorStore`

### 8. `scene.py`（~280 行）

独立类，不依赖 `BookIndexRepository`：

```python
# 搬入内容：
@dataclass FilterThresholds
class CharacterRegistryBuilder
class SceneSegmentBuilder
def build_chapter_chunks(scenes, chunk_size=420, overlap=80) -> list[dict]
```

依赖：`constants.py`（`PERSON_RE`、`TITLE_PERSON_RE`、`STOP_NAMES`、`BAD_NAME_ENDINGS`、`LOCATION_SHIFT_RE`）、`jieba.posseg`

### 9. `__init__.py`

```python
from .models import LoadedBookIndex, scope_filter
from .repository import BookIndexRepository
from .scene import CharacterRegistryBuilder, SceneSegmentBuilder, FilterThresholds, build_chapter_chunks

__all__ = [
    "BookIndexRepository",
    "LoadedBookIndex",
    "scope_filter",
    "CharacterRegistryBuilder",
    "SceneSegmentBuilder",
    "FilterThresholds",
    "build_chapter_chunks",
]
```

---

## 执行步骤

### Phase 1：创建包结构（无功能变更）

1. 创建 `novel_system/indexing/` 目录
2. 将原 `novel_system/indexing.py` 重命名为 `novel_system/indexing_legacy.py`（备份）
3. 创建空的 `__init__.py`，暂时从 `indexing_legacy` 重新导出所有公共符号
4. 运行 `pytest` 确认无回归

### Phase 2：抽出纯函数模块（风险最低）

5. 创建 `constants.py`，搬入所有模块级常量
6. 创建 `models.py`，搬入 `LoadedBookIndex` 和 `scope_filter`
7. 创建 `parser.py`，搬入解析相关函数
8. 更新 `indexing_legacy.py` 中对应位置改为 `from .indexing.constants import ...`
9. 运行 `pytest`

### Phase 3：抽出 scene 模块

10. 创建 `scene.py`，搬入 `FilterThresholds`、`CharacterRegistryBuilder`、`SceneSegmentBuilder`、`build_chapter_chunks`
11. 运行 `pytest`

### Phase 4：抽出 LLM 和向量模块

12. 创建 `llm_extraction.py`，搬入 LLM 相关函数
13. 创建 `vector_indexing.py`，搬入向量化相关函数
14. 运行 `pytest`

### Phase 5：抽出 artifact builders

15. 创建 `artifact_builders.py`，将所有 `_build_*` 方法改为独立函数
16. 修改 `repository.py` 中 `build_from_txt` 调用新函数
17. 运行 `pytest`

### Phase 6：收尾

18. 将 `indexing_legacy.py` 剩余内容整理为 `repository.py`
19. 更新 `__init__.py` 为最终版本
20. 删除 `indexing_legacy.py`
21. 全局搜索 `from .indexing import` 和 `from novel_system.indexing import`，确认所有外部引用正常
22. 运行完整测试套件
23. 删除备份

---

## 外部引用影响

需要检查并更新以下文件中的 import：

| 文件 | 当前 import | 变更 |
|------|-------------|------|
| `novel_system/service.py` | `from .indexing import BookIndexRepository, LoadedBookIndex` | 无需变更（`__init__.py` 重新导出） |
| `novel_system/api.py` | `from .indexing import ...` | 无需变更 |
| `novel_system/retrieval.py` | `from .indexing import scope_filter` | 无需变更 |
| `tests/test_indexing.py` | `from novel_system.indexing import ...` | 无需变更 |
| `scripts/build_index.py` | `from novel_system.indexing import BookIndexRepository` | 无需变更 |

所有外部 import 通过 `__init__.py` 重新导出，无需修改。

---

## 风险与回退

- **回退方案**：每个 Phase 结束后如果测试失败，恢复 `indexing_legacy.py` 即可回到上一个稳定状态
- **循环依赖风险**：`artifact_builders.py` 依赖 `llm_extraction.py` 的提取结果 — 通过参数传入而非 import 解决
- **状态耦合**：`_active_llm_extractions` 当前挂在 `self` 上 — 重构后改为 `build_from_txt` 内的局部变量，作为参数传递给各 builder

---

## 验证清单

- [ ] `pytest` 全部通过
- [ ] `from novel_system.indexing import BookIndexRepository, LoadedBookIndex` 正常工作
- [ ] `python scripts/build_index.py` 能正常构建索引
- [ ] API 启动后，前端所有功能正常（问答、续写、图谱、评测）
- [ ] 无循环 import 错误
