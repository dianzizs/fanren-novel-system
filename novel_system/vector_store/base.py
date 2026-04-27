"""Vector Store 抽象基类"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class VectorSearchResult:
    """向量搜索结果。"""

    id: str
    score: float
    document: dict[str, Any]
    vector: Optional[list[float]] = None


class BaseVectorStore(ABC):
    """向量存储抽象基类。"""

    @abstractmethod
    def add(
        self,
        ids: list[str],
        vectors: list[list[float]],
        documents: list[dict[str, Any]],
    ) -> int:
        """
        添加向量到存储。

        Args:
            ids: 文档 ID 列表
            vectors: 向量列表
            documents: 文档元数据列表

        Returns:
            成功添加的数量
        """
        pass

    @abstractmethod
    def search(
        self,
        query_vector: list[float],
        top_k: int = 10,
        filter: Optional[dict[str, Any]] = None,
    ) -> list[VectorSearchResult]:
        """
        搜索相似向量。

        Args:
            query_vector: 查询向量
            top_k: 返回数量
            filter: 过滤条件（可选）

        Returns:
            搜索结果列表
        """
        pass

    @abstractmethod
    def delete(self, ids: list[str]) -> int:
        """
        删除向量。

        Args:
            ids: 要删除的 ID 列表

        Returns:
            成功删除的数量
        """
        pass

    @abstractmethod
    def get(self, ids: list[str]) -> list[VectorSearchResult]:
        """
        根据 ID 获取向量。

        Args:
            ids: ID 列表

        Returns:
            向量结果列表
        """
        pass

    @abstractmethod
    def count(self) -> int:
        """
        返回存储的向量数量。

        Returns:
            向量数量
        """
        pass

    @abstractmethod
    def save(self, path: str) -> None:
        """
        保存索引到磁盘。

        Args:
            path: 保存路径
        """
        pass

    @abstractmethod
    def load(self, path: str) -> None:
        """
        从磁盘加载索引。

        Args:
            path: 索引路径
        """
        pass

    @property
    @abstractmethod
    def dimension(self) -> int:
        """向量维度。"""
        pass

    @property
    @abstractmethod
    def is_ready(self) -> bool:
        """检查存储是否可用。"""
        pass
