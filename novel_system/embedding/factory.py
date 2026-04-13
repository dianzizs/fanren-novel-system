"""Embedding Provider 工厂函数"""

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from .base import EmbeddingProvider
from .local_openvino import LocalOpenVINOEmbeddingProvider

if TYPE_CHECKING:
    from novel_system.config import AppConfig

logger = logging.getLogger(__name__)


def create_embedding_provider(config: "AppConfig") -> EmbeddingProvider:
    """
    创建 Embedding Provider 实例

    Args:
        config: 应用配置

    Returns:
        EmbeddingProvider 实例

    Raises:
        RuntimeError: 如果创建失败
    """
    provider_type = config.embedding_provider

    if provider_type == "local_openvino":
        logger.info(f"Creating LocalOpenVINOEmbeddingProvider with model {config.local_embedding_model}")
        return LocalOpenVINOEmbeddingProvider(
            model_name=config.local_embedding_model,
            device=config.local_embedding_device,
            fallback_device=config.local_embedding_fallback_device,
            batch_size=config.local_embedding_batch_size,
            normalize=config.local_embedding_normalize,
            cache_dir=config.local_embedding_cache_dir,
        )
    else:
        raise ValueError(f"Unknown embedding provider: {provider_type}")
