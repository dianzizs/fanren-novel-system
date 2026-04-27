"""FAISS-based Vector Store Implementation."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

import numpy as np

from .base import BaseVectorStore, VectorSearchResult

logger = logging.getLogger(__name__)


class FAISSVectorStore(BaseVectorStore):
    """
    基于 FAISS 的向量存储实现。

    支持：
    - CPU 和 GPU 索引
    - L2 距离或内积相似度
    - 增量添加向量
    - 磁盘持久化
    """

    def __init__(
        self,
        dimension: int = 512,
        metric: str = "ip",
        use_gpu: bool = False,
        nlist: int = 100,
    ):
        """
        初始化 FAISS 向量存储。

        Args:
            dimension: 向量维度
            metric: 距离度量 ("ip" 内积 | "l2" 欧氏距离)
            use_gpu: 是否使用 GPU 加速
            nlist: IVF 索引的聚类数量（数据量大时使用）
        """
        self._dimension = dimension
        self._metric = metric.lower()
        self._use_gpu = use_gpu
        self._nlist = nlist

        # 索引和元数据
        self._index: Optional[Any] = None
        self._id_to_idx: dict[str, int] = {}
        self._idx_to_id: dict[int, str] = {}
        self._documents: dict[str, dict[str, Any]] = {}
        self._next_idx: int = 0

        # GPU 资源
        self._gpu_res: Optional[Any] = None

        self._initialize_index()

    def _initialize_index(self) -> None:
        """初始化 FAISS 索引。"""
        import faiss

        # 创建基础索引
        if self._metric == "ip":
            self._index = faiss.IndexFlatIP(self._dimension)
        else:
            self._index = faiss.IndexFlatL2(self._dimension)

        # GPU 加速
        if self._use_gpu:
            try:
                res = faiss.StandardGpuResources()
                self._index = faiss.index_cpu_to_gpu(res, 0, self._index)
                self._gpu_res = res
                logger.info("FAISS index moved to GPU")
            except Exception as e:
                logger.warning(f"Failed to move FAISS to GPU: {e}, using CPU")
                self._use_gpu = False

        logger.info(
            f"Initialized FAISS index: dimension={self._dimension}, "
            f"metric={self._metric}, gpu={self._use_gpu}"
        )

    def add(
        self,
        ids: list[str],
        vectors: list[list[float]],
        documents: list[dict[str, Any]],
    ) -> int:
        """添加向量到存储。"""
        if not ids or not vectors:
            return 0

        if len(ids) != len(vectors) or len(ids) != len(documents):
            raise ValueError("ids, vectors, and documents must have same length")

        # 转换为 numpy 数组
        vectors_np = np.array(vectors, dtype=np.float32)

        # 过滤已存在的 ID
        new_ids = []
        new_vectors = []
        new_docs = []
        indices = []

        for i, id_ in enumerate(ids):
            if id_ in self._id_to_idx:
                logger.debug(f"ID {id_} already exists, skipping")
                continue
            new_ids.append(id_)
            new_vectors.append(vectors[i])
            new_docs.append(documents[i])
            indices.append(self._next_idx)
            self._next_idx += 1

        if not new_ids:
            return 0

        # 添加到索引
        new_vectors_np = np.array(new_vectors, dtype=np.float32)
        start_idx = self._index.ntotal
        self._index.add(new_vectors_np)

        # 更新映射
        for i, (id_, doc, idx) in enumerate(zip(new_ids, new_docs, indices)):
            actual_idx = start_idx + i
            self._id_to_idx[id_] = actual_idx
            self._idx_to_id[actual_idx] = id_
            self._documents[id_] = doc

        logger.debug(f"Added {len(new_ids)} vectors to FAISS index")
        return len(new_ids)

    def search(
        self,
        query_vector: list[float],
        top_k: int = 10,
        filter: Optional[dict[str, Any]] = None,
    ) -> list[VectorSearchResult]:
        """搜索相似向量。"""
        if self._index.ntotal == 0:
            return []

        # 转换查询向量
        query_np = np.array([query_vector], dtype=np.float32)

        # 搜索
        distances, indices = self._index.search(query_np, min(top_k, self._index.ntotal))

        results = []
        for dist, idx in zip(distances[0], indices[0]):
            if idx < 0:
                continue

            id_ = self._idx_to_id.get(idx)
            if id_ is None:
                continue

            doc = self._documents.get(id_, {})

            # 应用过滤器
            if filter:
                match = all(doc.get(k) == v for k, v in filter.items())
                if not match:
                    continue

            results.append(
                VectorSearchResult(
                    id=id_,
                    score=float(dist),
                    document=doc,
                )
            )

        return results

    def delete(self, ids: list[str]) -> int:
        """
        删除向量（标记删除）。

        注意：FAISS 不支持真正的删除，此方法仅从映射中移除。
        如需真正删除，需要重建索引。
        """
        count = 0
        for id_ in ids:
            if id_ in self._id_to_idx:
                idx = self._id_to_idx.pop(id_)
                self._idx_to_id.pop(idx, None)
                self._documents.pop(id_, None)
                count += 1

        if count > 0:
            logger.debug(f"Marked {count} vectors as deleted")

        return count

    def get(self, ids: list[str]) -> list[VectorSearchResult]:
        """根据 ID 获取向量。"""
        results = []
        for id_ in ids:
            if id_ in self._documents:
                results.append(
                    VectorSearchResult(
                        id=id_,
                        score=1.0,
                        document=self._documents[id_],
                    )
                )
        return results

    def count(self) -> int:
        """返回有效向量数量。"""
        return len(self._id_to_idx)

    def save(self, path: str) -> None:
        """保存索引和元数据到磁盘。"""
        import faiss

        save_path = Path(path)
        save_path.mkdir(parents=True, exist_ok=True)

        # 如果是 GPU 索引，先转回 CPU
        index_to_save = self._index
        if self._use_gpu and self._gpu_res is not None:
            index_to_save = faiss.index_gpu_to_cpu(self._index)

        # 保存 FAISS 索引
        faiss.write_index(index_to_save, str(save_path / "index.faiss"))

        # 保存元数据
        metadata = {
            "dimension": self._dimension,
            "metric": self._metric,
            "id_to_idx": self._id_to_idx,
            "idx_to_id": {str(k): v for k, v in self._idx_to_id.items()},
            "documents": self._documents,
            "next_idx": self._next_idx,
        }
        with open(save_path / "metadata.json", "w", encoding="utf-8") as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)

        logger.info(f"Saved FAISS index to {path}")

    def load(self, path: str) -> None:
        """从磁盘加载索引和元数据。"""
        import faiss

        load_path = Path(path)

        if not load_path.exists():
            raise FileNotFoundError(f"Path not found: {path}")

        # 加载 FAISS 索引
        self._index = faiss.read_index(str(load_path / "index.faiss"))

        # 移动到 GPU（如果启用）
        if self._use_gpu:
            try:
                res = faiss.StandardGpuResources()
                self._index = faiss.index_cpu_to_gpu(res, 0, self._index)
                self._gpu_res = res
            except Exception as e:
                logger.warning(f"Failed to move FAISS to GPU: {e}")
                self._use_gpu = False

        # 加载元数据
        with open(load_path / "metadata.json", "r", encoding="utf-8") as f:
            metadata = json.load(f)

        self._id_to_idx = metadata["id_to_idx"]
        self._idx_to_id = {int(k): v for k, v in metadata["idx_to_id"].items()}
        self._documents = metadata["documents"]
        self._next_idx = metadata["next_idx"]

        logger.info(f"Loaded FAISS index from {path}, count={self.count()}")

    @property
    def dimension(self) -> int:
        """向量维度。"""
        return self._dimension

    @property
    def is_ready(self) -> bool:
        """检查存储是否可用。"""
        return self._index is not None

    def compact(self) -> None:
        """
        压缩索引，移除已删除的向量。

        这会重建索引，适用于有大量删除后的场景。
        """
        if not self._id_to_idx:
            return

        import faiss

        # 收集有效向量
        valid_ids = list(self._id_to_idx.keys())
        valid_vectors = []

        # 重建索引需要从原始索引中提取向量
        # FAISS IndexFlat 可以直接获取向量
        if hasattr(self._index, "xb"):
            all_vectors = self._index.xb
            for id_ in valid_ids:
                idx = self._id_to_idx[id_]
                valid_vectors.append(all_vectors[idx].tolist())

        if not valid_vectors:
            return

        # 重建索引
        self._initialize_index()
        self._id_to_idx = {}
        self._idx_to_id = {}
        self._next_idx = 0

        # 重新添加
        docs = [self._documents[id_] for id_ in valid_ids]
        self.add(valid_ids, valid_vectors, docs)

        logger.info(f"Compacted FAISS index, now has {self.count()} vectors")
