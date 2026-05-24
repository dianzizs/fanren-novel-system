from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from ..vector_store.base import BaseVectorStore

@dataclass
class LoadedBookIndex:
    """加载后的书籍索引数据。

    包含书籍的元数据、章节内容、各类索引制品和向量化数据。
    """

    manifest: dict[str, Any]
    chapters: list[dict[str, Any]]
    corpora: dict[str, list[dict[str, Any]]]
    vectorizers: dict[str, TfidfVectorizer]
    matrices: dict[str, Any]
    vector_stores: dict[str, BaseVectorStore]
    graph: Optional[Any] = None


def scope_filter(chapter: int, chapter_scope: list[int]) -> bool:
    if not chapter_scope:
        return True
    if len(chapter_scope) == 1:
        return chapter == chapter_scope[0]
    start, end = min(chapter_scope), max(chapter_scope)
    return start <= chapter <= end
