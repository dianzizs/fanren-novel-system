"""Tests for EmbeddingProvider module"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

from novel_system.embedding.base import EmbeddingProvider, ModelInfo
from novel_system.embedding.factory import create_embedding_provider


class MockEmbeddingProvider(EmbeddingProvider):
    """Mock implementation for testing"""

    def __init__(self, model_info: ModelInfo):
        self._model_info = model_info
        self._ready = True

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[0.1, 0.2, 0.3] for _ in texts]

    def get_model_info(self) -> ModelInfo:
        return self._model_info

    def is_ready(self) -> bool:
        return self._ready


class TestModelInfo:
    """Tests for ModelInfo dataclass"""

    def test_model_info_creation(self):
        info = ModelInfo(
            provider="local_openvino",
            device="GPU",
            model_name="bge-small-zh-v1.5",
            dimension=512,
            normalized=True,
        )
        assert info.provider == "local_openvino"
        assert info.device == "GPU"
        assert info.model_name == "bge-small-zh-v1.5"
        assert info.dimension == 512
        assert info.normalized is True


class TestEmbeddingProvider:
    """Tests for EmbeddingProvider abstract class"""

    def test_mock_provider_embed(self):
        info = ModelInfo(
            provider="mock",
            device="CPU",
            model_name="test-model",
            dimension=3,
            normalized=True,
        )
        provider = MockEmbeddingProvider(info)

        result = provider.embed(["hello", "world"])
        assert len(result) == 2
        assert result[0] == [0.1, 0.2, 0.3]

    def test_mock_provider_is_ready(self):
        info = ModelInfo(
            provider="mock",
            device="CPU",
            model_name="test-model",
            dimension=3,
            normalized=True,
        )
        provider = MockEmbeddingProvider(info)
        assert provider.is_ready() is True


class TestCreateEmbeddingProvider:
    """Tests for factory function"""

    def test_create_unknown_provider_raises(self):
        mock_config = Mock()
        mock_config.embedding_provider = "unknown_provider"

        with pytest.raises(ValueError, match="Unknown embedding provider"):
            create_embedding_provider(mock_config)

    @patch("novel_system.embedding.factory.LocalOpenVINOEmbeddingProvider")
    def test_create_local_openvino_provider(self, mock_provider_class):
        mock_config = Mock()
        mock_config.embedding_provider = "local_openvino"
        mock_config.local_embedding_model = "BAAI/bge-small-zh-v1.5"
        mock_config.local_embedding_device = "GPU"
        mock_config.local_embedding_fallback_device = "CPU"
        mock_config.local_embedding_batch_size = 32
        mock_config.local_embedding_normalize = True
        mock_config.local_embedding_cache_dir = Path("data/runtime/models")

        mock_instance = Mock()
        mock_provider_class.return_value = mock_instance

        result = create_embedding_provider(mock_config)

        mock_provider_class.assert_called_once_with(
            model_name="BAAI/bge-small-zh-v1.5",
            device="GPU",
            fallback_device="CPU",
            batch_size=32,
            normalize=True,
            cache_dir=Path("data/runtime/models"),
        )
        assert result == mock_instance


class TestLocalOpenVINOEmbeddingProvider:
    """Tests for LocalOpenVINOEmbeddingProvider"""

    def test_provider_initialization_attributes(self):
        """Test provider stores initialization attributes correctly"""
        from novel_system.embedding.local_openvino import LocalOpenVINOEmbeddingProvider

        # Skip actual model loading by mocking _initialize_model
        with patch.object(
            LocalOpenVINOEmbeddingProvider,
            "_initialize_model",
        ):
            provider = LocalOpenVINOEmbeddingProvider(
                model_name="BAAI/bge-small-zh-v1.5",
                device="GPU",
                fallback_device="CPU",
                batch_size=32,
                normalize=True,
            )

            assert provider.model_name == "BAAI/bge-small-zh-v1.5"
            assert provider.preferred_device == "GPU"
            assert provider.fallback_device == "CPU"
            assert provider.batch_size == 32
            assert provider.normalize is True

    def test_provider_embed_before_ready_raises(self):
        """Test embed raises if model not ready"""
        from novel_system.embedding.local_openvino import LocalOpenVINOEmbeddingProvider

        provider = LocalOpenVINOEmbeddingProvider.__new__(LocalOpenVINOEmbeddingProvider)
        provider._model = None
        provider._dimension = None

        with pytest.raises(RuntimeError, match="Model not loaded"):
            provider.embed(["test"])
