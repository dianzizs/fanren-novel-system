"""Embedding Provider 抽象基类"""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class ModelInfo:
    """模型信息，用于缓存校验"""

    provider: str  # "local_openvino"
    device: str  # "GPU" | "CPU"
    model_name: str  # "bge-small-zh-v1.5"
    dimension: int  # 512
    normalized: bool  # True


class EmbeddingProvider(ABC):
    """Embedding Provider 抽象基类"""

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        """
        批量计算 embedding

        Args:
            texts: 文本列表

        Returns:
            embedding 向量列表
        """
        pass

    @abstractmethod
    def get_model_info(self) -> ModelInfo:
        """
        返回模型信息，用于缓存校验

        Returns:
            ModelInfo 实例
        """
        pass

    @abstractmethod
    def is_ready(self) -> bool:
        """
        检查模型是否已加载

        Returns:
            True 如果模型已加载且可用
        """
        pass
