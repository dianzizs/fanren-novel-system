"""Local CUDA-accelerated Embedding Provider using SentenceTransformers."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from .base import EmbeddingProvider, ModelInfo

logger = logging.getLogger(__name__)


class LocalCUDAEmbeddingProvider(EmbeddingProvider):
    """
    本地 CUDA 加速的 Embedding Provider

    使用 SentenceTransformers 库，支持 NVIDIA GPU (CUDA) 加速。
    适用于拥有 NVIDIA GPU 的系统。
    """

    def __init__(
        self,
        model_name: str = "BAAI/bge-small-zh-v1.5",
        device: str = "cuda",
        batch_size: int = 32,
        normalize: bool = True,
        cache_dir: Optional[Path] = None,
    ):
        """
        初始化 CUDA embedding provider

        Args:
            model_name: HuggingFace 模型名称
            device: 设备 ("cuda" | "cpu")
            batch_size: 批量推理大小
            normalize: 是否归一化输出向量
            cache_dir: 模型缓存目录
        """
        self.model_name = model_name
        self.device = device
        self.batch_size = batch_size
        self.normalize = normalize
        self.cache_dir = cache_dir or Path("data/runtime/models")

        # 模型实例
        self._model = None
        self._dimension: Optional[int] = None
        self._actual_device: Optional[str] = None

        # 初始化模型
        self._initialize_model()

    def _initialize_model(self) -> None:
        """初始化模型，尝试 CUDA，失败则降级到 CPU"""
        from sentence_transformers import SentenceTransformer
        import torch

        # 确保缓存目录存在
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # 检查 CUDA 是否可用
        device_lower = self.device.lower() if self.device else "cuda"
        if device_lower in ("cuda", "gpu"):
            if torch.cuda.is_available():
                logger.info(f"CUDA available: {torch.cuda.get_device_name(0)}")
                self._actual_device = "cuda"
            else:
                logger.warning("CUDA not available, falling back to CPU")
                self._actual_device = "cpu"
        else:
            self._actual_device = "cpu"

        # 加载模型
        logger.info(f"Loading embedding model {self.model_name} on {self._actual_device}...")
        self._model = SentenceTransformer(
            self.model_name,
            device=self._actual_device,
            cache_folder=str(self.cache_dir),
        )

        # 获取维度
        self._dimension = self._model.get_sentence_embedding_dimension()
        logger.info(
            f"Loaded embedding model {self.model_name} on {self._actual_device}, "
            f"dimension={self._dimension}"
        )

    def embed(self, texts: list[str]) -> list[list[float]]:
        """
        批量计算 embedding

        Args:
            texts: 文本列表

        Returns:
            embedding 向量列表
        """
        if not self.is_ready():
            raise RuntimeError("Model not loaded")

        # 使用 SentenceTransformer 的 encode 方法
        embeddings = self._model.encode(
            texts,
            batch_size=self.batch_size,
            normalize_embeddings=self.normalize,
            show_progress_bar=False,
            convert_to_numpy=True,
        )

        return embeddings.tolist()

    def get_model_info(self) -> ModelInfo:
        """返回模型信息"""
        return ModelInfo(
            provider="local_cuda",
            device=self._actual_device or "unknown",
            model_name=self.model_name,
            dimension=self._dimension or 512,
            normalized=self.normalize,
        )

    def is_ready(self) -> bool:
        """检查模型是否已加载"""
        return self._model is not None and self._dimension is not None
