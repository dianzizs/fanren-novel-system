from unittest.mock import MagicMock, patch
from pathlib import Path
import json
from novel_system.config import AppConfig
from novel_system.indexing import BookIndexRepository

def test_structured_llm_extraction_fallback_when_disabled(tmp_path: Path):
    # When LLM is disabled, it should fall back to legacy regex
    config = AppConfig(
        root_dir=tmp_path,
        data_dir=tmp_path / "data",
        runtime_dir=tmp_path / "data" / "runtime",
        books_dir=tmp_path / "data" / "books",
        default_book_id="test",
        default_book_title="Test",
        default_book_path=tmp_path / "test.txt",
        minimax_api_key="", # Disabled
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
    repo = BookIndexRepository(config)
    chapters = [
        {
            "chapter": 1,
            "title": "第1章",
            "text": "韩立、南宫婉相视一笑。",
            "paragraphs": ["韩立、南宫婉相视一笑。"]
        }
    ]
    cards = repo._build_character_cards(chapters, "test-book")
    card_names = {c["name"] for c in cards}
    assert "韩立" in card_names

@patch("novel_system.embedding.local_openvino.LocalOpenVINOEmbeddingProvider._initialize_model")
def test_structured_llm_extraction_active_when_enabled(mock_init_model, tmp_path: Path):
    config = AppConfig(
        root_dir=tmp_path,
        data_dir=tmp_path / "data",
        runtime_dir=tmp_path / "data" / "runtime",
        books_dir=tmp_path / "data" / "books",
        default_book_id="test",
        default_book_title="Test",
        default_book_path=tmp_path / "test.txt",
        minimax_api_key="mock-key", # Enabled
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
    repo = BookIndexRepository(config)
    
    mock_response = {
        "characters": [
            {"name": "韩立", "aliases": ["二愣子"], "description": "主角"},
            {"name": "墨大夫", "aliases": ["墨老"], "description": "师父"}
        ],
        "relationships": [
            {"source": "韩立", "target": "墨大夫", "description": "师徒"}
        ],
        "events": [
            {"description": "韩立遇到了墨大夫", "participants": ["韩立", "墨大夫"]}
        ]
    }
    
    with patch("novel_system.llm.MiniMaxClient") as MockClient:
        instance = MockClient.return_value
        instance.enabled = True
        instance.chat.return_value = MagicMock(content=json.dumps(mock_response), usage={"total_tokens": 100})
        
        test_file = tmp_path / "source.txt"
        test_file.write_text("第1章 第一章\n韩立在神手谷遇到了墨大夫。", encoding="utf-8")
        
        repo.build_from_txt("test-book", "Test Book", test_file)
        
        assert instance.chat.call_count > 0
