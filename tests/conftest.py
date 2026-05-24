import hashlib
import tempfile
from pathlib import Path
from typing import Generator

import numpy as np
import pytest

from novel_system.config import AppConfig
from novel_system.indexing import BookIndexRepository


class MockEmbeddingProvider:
    """Mock embedding provider for testing."""

    def __init__(self, dimension: int = 128):
        self._dimension = dimension
        self._call_count = 0

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Generate deterministic embeddings based on text hash."""
        self._call_count += 1
        results = []
        for text in texts:
            # Use hashlib for deterministic seeding (hash() is randomized per process)
            seed = int(hashlib.md5(text.encode("utf-8")).hexdigest(), 16) % (2**31)
            np.random.seed(seed)
            vector = np.random.randn(self._dimension).astype(np.float32)
            # Normalize
            vector = vector / np.linalg.norm(vector)
            results.append(vector.tolist())
        return results

    @property
    def ready(self) -> bool:
        return True


@pytest.fixture
def tmp_app_dir() -> Generator[Path, None, None]:
    with tempfile.TemporaryDirectory() as tmp_dir:
        yield Path(tmp_dir)


@pytest.fixture
def test_config(tmp_app_dir: Path) -> AppConfig:
    """Create test configuration."""
    data_dir = tmp_app_dir / "data"
    return AppConfig(
        root_dir=tmp_app_dir,
        data_dir=data_dir,
        runtime_dir=data_dir / "runtime",
        books_dir=data_dir / "books",
        default_book_id="test-book",
        default_book_title="Test Book",
        default_book_path=tmp_app_dir / "test.txt",
        minimax_api_key="",
        minimax_base_url="https://api.minimax.chat/v1",
        minimax_chat_model="MiniMax-m2.7-HighSpeed",
        embedding_provider="local_openvino",
        local_embedding_model="BAAI/bge-small-zh-v1.5",
        local_embedding_device="CPU",
        local_embedding_fallback_device="CPU",
        local_embedding_batch_size=32,
        local_embedding_normalize=True,
        local_embedding_cache_dir=tmp_app_dir / "cache",
        vector_store_dir=data_dir / "vectors",
        trace_enabled=False,
        trace_log_level="INFO",
        dense_search_overfetch_factor=10,
    )


@pytest.fixture
def test_book_content() -> str:
    """Create test book content with chapters."""
    return """第1章 开始
韩立是一个普通的少年，生活在青牛镇。
他和张铁一起在七玄门学艺。
第2章 修炼
韩立开始修炼长春功。
墨大夫教导他医术和毒术。
第3章 考验
韩立通过了外门弟子的考验。
他获得了升仙令。
"""


@pytest.fixture
def mock_embedding_provider() -> MockEmbeddingProvider:
    return MockEmbeddingProvider(dimension=128)


@pytest.fixture
def test_repo(test_config: AppConfig, mock_embedding_provider: MockEmbeddingProvider) -> BookIndexRepository:
    """Create a repository instance with a mock embedding provider."""
    return BookIndexRepository(test_config, embedding_provider=mock_embedding_provider)
