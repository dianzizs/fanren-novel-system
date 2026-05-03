"""Tests for event_timeline quality and event sentence recognition."""
from novel_system.indexing import BookIndexRepository


def test_score_event_sentence_action_verbs():
    """Sentences with action verbs should score higher."""
    # Need to instantiate to access the method
    from novel_system.config import AppConfig
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        config = AppConfig(
            root_dir=Path(tmp),
            data_dir=Path(tmp) / "data",
            runtime_dir=Path(tmp) / "data" / "runtime",
            books_dir=Path(tmp) / "data" / "books",
            default_book_id="test",
            default_book_title="Test",
            default_book_path=Path(tmp) / "test.txt",
            minimax_api_key="",
            minimax_base_url="https://api.minimax.chat/v1",
            minimax_chat_model="MiniMax-m2.7-HighSpeed",
            embedding_provider="local_openvino",
            local_embedding_model="BAAI/bge-small-zh-v1.5",
            local_embedding_device="CPU",
            local_embedding_fallback_device="CPU",
            local_embedding_batch_size=32,
            local_embedding_normalize=True,
            local_embedding_cache_dir=Path(tmp) / "cache",
            vector_store_dir=Path(tmp) / "data" / "vectors",
            trace_enabled=False,
            trace_log_level="INFO",
            dense_search_overfetch_factor=10,
        )
        repo = BookIndexRepository(config)

        # Sentence with action verb
        action_sentence = "韩立终于发现了小绿瓶的秘密。"
        normal_sentence = "韩立觉得这个地方很不错。"

        action_score = repo._score_event_sentence(action_sentence)
        normal_score = repo._score_event_sentence(normal_sentence)

        assert action_score > normal_score, "Action sentence should score higher"


def test_score_event_sentence_time_words():
    """Sentences with time words should score higher."""
    from novel_system.config import AppConfig
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        config = AppConfig(
            root_dir=Path(tmp),
            data_dir=Path(tmp) / "data",
            runtime_dir=Path(tmp) / "data" / "runtime",
            books_dir=Path(tmp) / "data" / "books",
            default_book_id="test",
            default_book_title="Test",
            default_book_path=Path(tmp) / "test.txt",
            minimax_api_key="",
            minimax_base_url="https://api.minimax.chat/v1",
            minimax_chat_model="MiniMax-m2.7-HighSpeed",
            embedding_provider="local_openvino",
            local_embedding_model="BAAI/bge-small-zh-v1.5",
            local_embedding_device="CPU",
            local_embedding_fallback_device="CPU",
            local_embedding_batch_size=32,
            local_embedding_normalize=True,
            local_embedding_cache_dir=Path(tmp) / "cache",
            vector_store_dir=Path(tmp) / "data" / "vectors",
            trace_enabled=False,
            trace_log_level="INFO",
            dense_search_overfetch_factor=10,
        )
        repo = BookIndexRepository(config)

        time_sentence = "几天后，韩立决定离开七玄门。"
        static_sentence = "韩立住在七玄门。"

        time_score = repo._score_event_sentence(time_sentence)
        static_score = repo._score_event_sentence(static_sentence)

        assert time_score > static_score, "Sentence with time word should score higher"


def test_score_event_sentence_causality():
    """Sentences with causality words should score higher."""
    from novel_system.config import AppConfig
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        config = AppConfig(
            root_dir=Path(tmp),
            data_dir=Path(tmp) / "data",
            runtime_dir=Path(tmp) / "data" / "runtime",
            books_dir=Path(tmp) / "data" / "books",
            default_book_id="test",
            default_book_title="Test",
            default_book_path=Path(tmp) / "test.txt",
            minimax_api_key="",
            minimax_base_url="https://api.minimax.chat/v1",
            minimax_chat_model="MiniMax-m2.7-HighSpeed",
            embedding_provider="local_openvino",
            local_embedding_model="BAAI/bge-small-zh-v1.5",
            local_embedding_device="CPU",
            local_embedding_fallback_device="CPU",
            local_embedding_batch_size=32,
            local_embedding_normalize=True,
            local_embedding_cache_dir=Path(tmp) / "cache",
            vector_store_dir=Path(tmp) / "data" / "vectors",
            trace_enabled=False,
            trace_log_level="INFO",
            dense_search_overfetch_factor=10,
        )
        repo = BookIndexRepository(config)

        causal_sentence = "因为小绿瓶的秘密被发现，韩立不得不逃离。"
        plain_sentence = "韩立有一个小绿瓶。"

        causal_score = repo._score_event_sentence(causal_sentence)
        plain_score = repo._score_event_sentence(plain_sentence)

        assert causal_score > plain_score, "Causal sentence should score higher"


def test_build_event_timeline_prioritizes_event_sentences():
    """Event timeline should prioritize event-like sentences over first sentences."""
    from novel_system.index_pipeline import build_book_artifacts

    # Chapter with descriptive opening followed by key events
    chapters = [
        {
            "chapter": 1,
            "title": "测试章节",
            "paragraphs": [
                "这是一段普通的开场白，描述着风景和环境，没有任何事件发生。",
                "这里继续描述天气很好，阳光明媚，一切都很平静。",
                "突然，韩立发现了小绿瓶的秘密，决定立刻离开这个地方。",
                "因为这件事，他遇到了张铁，两人一起逃离了七玄门。",
                "几天后，他们成功到达了安全的地方。",
            ],
        }
    ]

    artifacts = build_book_artifacts(chapters)
    timeline = artifacts.get("event_timeline", [])

    assert len(timeline) >= 1
    # Check that the event text contains key event words
    event_text = timeline[0].get("text", "") or timeline[0].get("summary", "")

    # Event timeline should contain key event words, not just opening description
    assert "小绿瓶" in event_text or "逃离" in event_text or "发现" in event_text, (
        f"Event timeline should contain key events, got: {event_text}"
    )


def test_build_event_timeline_multiple_chapters():
    """Event timeline should work across multiple chapters."""
    from novel_system.index_pipeline import build_book_artifacts

    chapters = [
        {
            "chapter": 1,
            "title": "第一章",
            "text": "韩立发现了小绿瓶的秘密。他决定修炼。几天后他突破了。",
            "paragraphs": ["测试"],
        },
        {
            "chapter": 2,
            "title": "第二章",
            "text": "张铁遇到了韩立。于是他们一起行动。后来他们到达了目的地。",
            "paragraphs": ["测试"],
        },
    ]

    artifacts = build_book_artifacts(chapters)
    timeline = artifacts.get("event_timeline", [])

    assert len(timeline) == 2
    assert timeline[0]["chapter"] == 1
    assert timeline[1]["chapter"] == 2


def test_event_timeline_has_required_fields():
    """Event timeline entries should have all required fields."""
    from novel_system.index_pipeline import build_book_artifacts

    chapters = [
        {
            "chapter": 1,
            "title": "测试",
            "paragraphs": ["韩立修炼了很久，终于突破了筑基期。"],
        }
    ]

    artifacts = build_book_artifacts(chapters)
    timeline = artifacts.get("event_timeline", [])

    assert len(timeline) == 1
    entry = timeline[0]

    # Core fields that must exist
    required_fields = ["id", "chapter", "title", "text", "participants", "source"]
    for field in required_fields:
        assert field in entry, f"Missing field: {field}"

    # Should have either text, summary, or description
    has_text = "text" in entry or "summary" in entry or "description" in entry
    assert has_text, "Event entry should have text content"
