"""Local OpenVINO Embedding Provider"""

import logging
import os
from pathlib import Path
from typing import Optional

from .base import EmbeddingProvider, ModelInfo

logger = logging.getLogger(__name__)


class LocalOpenVINOEmbeddingProvider(EmbeddingProvider):
    """
    本地 OpenVINO 加速的 Embedding Provider

    支持 Intel GPU (Arc) 加速，自动降级到 CPU。
    首次加载时自动将 HuggingFace 模型转换为 OpenVINO IR 格式。
    """

    def __init__(
        self,
        model_name: str = "BAAI/bge-small-zh-v1.5",
        device: str = "GPU",
        fallback_device: str = "CPU",
        batch_size: int = 32,
        normalize: bool = True,
        cache_dir: Optional[Path] = None,
    ):
        """
        初始化本地 embedding provider

        Args:
            model_name: HuggingFace 模型名称
            device: 首选设备 ("GPU" | "CPU")
            fallback_device: 降级设备 ("CPU")
            batch_size: 批量推理大小
            normalize: 是否归一化输出向量
            cache_dir: OpenVINO IR 模型缓存目录
        """
        self.model_name = model_name
        self.preferred_device = device
        self.fallback_device = fallback_device
        self.batch_size = batch_size
        self.normalize = normalize
        self.cache_dir = cache_dir or Path("data/runtime/models")

        # 模型实例
        self._model = None
        self._device: Optional[str] = None
        self._dimension: Optional[int] = None

        # 初始化模型
        self._initialize_model()

    def _initialize_model(self) -> None:
        """初始化模型，尝试 GPU，失败则降级到 CPU"""
        try:
            self._try_load_model(self.preferred_device)
            self._device = self.preferred_device
            logger.info(
                f"Loaded embedding model {self.model_name} on {self._device}"
            )
        except Exception as e:
            logger.warning(
                f"Failed to load model on {self.preferred_device}: {e}. "
                f"Trying fallback device {self.fallback_device}"
            )
            try:
                self._try_load_model(self.fallback_device)
                self._device = self.fallback_device
                logger.info(
                    f"Loaded embedding model {self.model_name} on {self._device} (fallback)"
                )
            except Exception as fallback_error:
                raise RuntimeError(
                    f"Failed to load embedding model on both {self.preferred_device} "
                    f"and {self.fallback_device}. GPU error: {e}, CPU error: {fallback_error}"
                ) from fallback_error

    def _try_load_model(self, device: str) -> None:
        """尝试在指定设备上加载模型"""
        from optimum.intel import OVModelForFeatureExtraction
        from transformers import AutoTokenizer

        # 确保缓存目录存在
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # 模型缓存路径
        model_cache_path = self.cache_dir / self.model_name.replace("/", "_")

        # 检查是否已有导出的 IR 模型
        if not (model_cache_path / "model.xml").exists():
            logger.info(f"Exporting model {self.model_name} to OpenVINO IR format...")
            # 导出模型
            ov_model = OVModelForFeatureExtraction.from_pretrained(
                self.model_name,
                export=True,
                cache_dir=str(self.cache_dir),
            )
            ov_model.save_pretrained(str(model_cache_path))
            logger.info(f"Model exported to {model_cache_path}")

        # 加载模型
        self._model = OVModelForFeatureExtraction.from_pretrained(
            str(model_cache_path),
            device=device,
        )

        # 加载 tokenizer
        self._tokenizer = AutoTokenizer.from_pretrained(
            self.model_name,
            cache_dir=str(self.cache_dir),
        )

        # 推断维度（通过编码一个测试文本）
        test_embedding = self._encode_single("test")
        self._dimension = len(test_embedding)

    def _encode_single(self, text: str) -> list[float]:
        """编码单个文本，返回向量"""
        import numpy as np

        inputs = self._tokenizer(text, return_tensors="pt", padding=True, truncation=True)

        # 移动到正确的设备
        if hasattr(self._model, "device"):
            inputs = {k: v.to(self._model.device) for k, v in inputs.items()}

        outputs = self._model(**inputs)

        # 使用 mean pooling
        attention_mask = inputs["attention_mask"]
        embeddings = self._mean_pooling(outputs.last_hidden_state, attention_mask)

        if self.normalize:
            embeddings = self._normalize(embeddings)

        return embeddings[0].tolist()

    def _mean_pooling(self, hidden_state, attention_mask) -> "np.ndarray":
        """Mean Pooling"""
        import numpy as np
        import torch

        input_mask_expanded = attention_mask.unsqueeze(-1).expand(hidden_state.size()).float()
        sum_embeddings = torch.sum(hidden_state * input_mask_expanded, dim=1)
        sum_mask = torch.clamp(input_mask_expanded.sum(dim=1), min=1e-9)
        return (sum_embeddings / sum_mask).detach().cpu().numpy()

    def _normalize(self, embeddings: "np.ndarray") -> "np.ndarray":
        """L2 归一化"""
        import numpy as np

        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        norms = np.maximum(norms, 1e-9)  # 避免除零
        return embeddings / norms

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

        import numpy as np
        import torch

        results = []

        # 批量处理
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i:i + self.batch_size]

            # Tokenize
            inputs = self._tokenizer(
                batch,
                return_tensors="pt",
                padding=True,
                truncation=True,
                max_length=512,
            )

            # 移动到正确的设备
            if hasattr(self._model, "device"):
                inputs = {k: v.to(self._model.device) for k, v in inputs.items()}

            # 推理
            with torch.no_grad():
                outputs = self._model(**inputs)

            # Mean pooling
            attention_mask = inputs["attention_mask"]
            embeddings = self._mean_pooling(outputs.last_hidden_state, attention_mask)

            if self.normalize:
                embeddings = self._normalize(embeddings)

            results.extend(embeddings.tolist())

        return results

    def get_model_info(self) -> ModelInfo:
        """返回模型信息"""
        return ModelInfo(
            provider="local_openvino",
            device=self._device or "unknown",
            model_name=self.model_name,
            dimension=self._dimension or 512,
            normalized=self.normalize,
        )

    def is_ready(self) -> bool:
        """检查模型是否已加载"""
        return self._model is not None and self._dimension is not None
