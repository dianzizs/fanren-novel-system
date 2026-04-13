"""Tests for index pipeline and artifact management."""
from pathlib import Path

from novel_system.config import AppConfig
from novel_system.indexing import BookIndexRepository


def test_repository_reads_new_artifact_names(tmp_path: Path):
    config = AppConfig(
        root_dir=tmp_path,
        data_dir=tmp_path / "data",
        runtime_dir=tmp_path / "data" / "runtime",
        books_dir=tmp_path / "data" / "books",
        default_book_id="default-book",
        default_book_title="Default",
        default_book_path=tmp_path / "default.txt",
        minimax_api_key="",
        minimax_base_url="https://api.minimax.chat/v1",
        minimax_chat_model="MiniMax-m2.7-HighSpeed",
        embedding_provider="local_openvino",
        local_embedding_model="BAAI/bge-small-zh-v1.5",
        local_embedding_device="CPU",
        local_embedding_fallback_device="CPU",
        local_embedding_batch_size=32,
        local_embedding_normalize=True,
        local_embedding_cache_dir=tmp_path / "cache",
        trace_enabled=False,
        trace_log_level="INFO",
    )
    config.books_dir.mkdir(parents=True, exist_ok=True)
    book_dir = config.books_dir / "book-a"
    book_dir.mkdir(parents=True, exist_ok=True)
    (book_dir / "manifest.json").write_text(
        '{"id":"book-a","title":"A","artifact_version":"v2","available_artifacts":["scene_segments","character_registry"]}',
        encoding="utf-8",
    )
    (book_dir / "scene_segments.json").write_text("[]", encoding="utf-8")
    (book_dir / "character_registry.json").write_text("[]", encoding="utf-8")

    repo = BookIndexRepository(config)

    assert repo.read_artifact("book-a", "scene_segments") == []
    assert repo.read_artifact("book-a", "character_registry") == []


def test_pipeline_builds_scene_and_registry():
    """Pipeline 应构建场景片段和角色注册表。"""
    from novel_system.index_pipeline import build_book_artifacts

    chapters = [
        {
            "chapter": 1,
            "title": "山边小村",
            "text": "韩立。张铁。",
            "paragraphs": ["韩立。张铁。"],
        }
    ]

    artifacts = build_book_artifacts(chapters)

    assert "scene_segments" in artifacts
    assert "character_registry" in artifacts
    assert "chapter_chunks" in artifacts
    # 角色注册表应包含提取的角色
    assert len(artifacts["character_registry"]) >= 1


def test_pipeline_produces_complete_artifact_set():
    """Pipeline 应生成完整的 artifact 集合。"""
    from novel_system.index_pipeline import build_book_artifacts

    chapters = [
        {
            "chapter": 1,
            "title": "测试章节",
            "text": "韩立和张铁一起出现。",
            "paragraphs": ["韩立和张铁一起出现。"],
        }
    ]

    artifacts = build_book_artifacts(chapters)

    expected_artifacts = [
        "scene_segments",
        "character_registry",
        "chapter_chunks",
        "event_timeline",
        "character_card",
    ]

    for name in expected_artifacts:
        assert name in artifacts, f"Missing artifact: {name}"
