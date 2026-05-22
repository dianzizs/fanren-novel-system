import tempfile
from pathlib import Path
from unittest.mock import patch
from novel_system.config import AppConfig
from novel_system.service import NovelSystemService

@patch("novel_system.embedding.local_openvino.LocalOpenVINOEmbeddingProvider._initialize_model")
def test_token_usage_persistence(mock_init_model):
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        config = AppConfig(
            root_dir=tmp_path,
            data_dir=tmp_path / "data",
            runtime_dir=tmp_path / "data" / "runtime",
            books_dir=tmp_path / "data" / "books",
            default_book_id="test",
            default_book_title="Test",
            default_book_path=tmp_path / "test.txt",
            minimax_api_key="test-key",
            minimax_base_url="https://api.minimax.chat/v1",
            minimax_chat_model="MiniMax-m2.7-HighSpeed",
            embedding_provider="local_openvino",
            local_embedding_model="BAAI/bge-small-zh-v1.5",
            local_embedding_device="CPU",
            local_embedding_fallback_device="CPU",
            local_embedding_batch_size=32,
            local_embedding_normalize=True,
            local_embedding_cache_dir=tmp_path / "cache",
            vector_store_dir=tmp_path / "data" / "vectors",
            trace_enabled=False,
            trace_log_level="INFO",
            dense_search_overfetch_factor=10,
        )
        # Initialize service
        service = NovelSystemService(config)
        
        # Record usage
        service._record_token_usage("test-book", {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150})
        
        # Verify file exists on disk
        token_file = config.data_dir / "books" / "test-book" / "token_usage.json"
        assert token_file.exists()
        
        # Initialize a fresh service and check if loaded
        fresh_service = NovelSystemService(config)
        stats = fresh_service.get_token_stats()
        
        assert stats["total_tokens"] == 150
