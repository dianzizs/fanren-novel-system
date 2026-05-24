"""Tests for index pipeline and artifact management."""
from pathlib import Path

from novel_system.config import AppConfig
from novel_system.indexing import BookIndexRepository


def test_repository_reads_new_artifact_names(test_config: AppConfig):
    test_config.books_dir.mkdir(parents=True, exist_ok=True)
    book_dir = test_config.books_dir / "book-a"
    book_dir.mkdir(parents=True, exist_ok=True)
    (book_dir / "manifest.json").write_text(
        '{"id":"book-a","title":"A","artifact_version":"v2","available_artifacts":["scene_segments","character_registry"]}',
        encoding="utf-8",
    )
    (book_dir / "scene_segments.json").write_text("[]", encoding="utf-8")
    (book_dir / "character_registry.json").write_text("[]", encoding="utf-8")

    repo = BookIndexRepository(test_config)

    assert repo.read_artifact("book-a", "scene_segments") == []
    assert repo.read_artifact("book-a", "character_registry") == []


def test_pipeline_builds_scene_and_registry():
    """Pipeline 应构建场景片段和角色注册表。"""
    from novel_system.indexing import build_book_artifacts

    chapters = [
        {
            "chapter": 1,
            "title": "山边小村",
            "text": "韩立。张铁。",
            "paragraphs": ["韩立。张铁。"],
        },
        {
            "chapter": 2,
            "title": "七玄门",
            "text": "韩立。张铁。",
            "paragraphs": ["韩立。张铁。"],
        },
    ]

    artifacts = build_book_artifacts(chapters)

    assert "scene_segments" in artifacts
    assert "character_registry" in artifacts
    assert "chapter_chunks" in artifacts
    # 角色注册表应包含提取的角色 (frequency >= 2)
    assert len(artifacts["character_registry"]) >= 1


def test_pipeline_produces_complete_artifact_set():
    """Pipeline 应生成完整的 artifact 集合。"""
    from novel_system.indexing import build_book_artifacts

    chapters = [
        {
            "chapter": 1,
            "title": "测试章节",
            "text": "韩立。张铁。韩立。张铁。",
            "paragraphs": ["韩立。张铁。韩立。张铁。"],
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


def test_character_registry_filters_by_frequency():
    """Character registry should filter low-frequency noise."""
    from novel_system.indexing import build_book_artifacts

    # Create chapters with a high-frequency character and low-frequency noise
    # Use proper punctuation after names so the regex extracts names correctly
    chapters = [
        {
            "chapter": 1,
            "title": "Chapter 1",
            "text": "韩立。张铁。",
            "paragraphs": ["韩立。张铁。"],
        },
        {
            "chapter": 2,
            "title": "Chapter 2",
            "text": "韩立。王护法。",
            "paragraphs": ["韩立。王护法。"],
        },
    ]

    artifacts = build_book_artifacts(chapters)
    registry = artifacts["character_registry"]

    # 韩立 should appear in registry (frequency >= 2)
    han_li_entries = [r for r in registry if r.get("canonical_name") == "韩立"]
    assert len(han_li_entries) >= 1, f"韩立 should be in registry, got: {[r['canonical_name'] for r in registry]}"


def test_character_registry_includes_canonical_names():
    """Character registry entries should have canonical names."""
    from novel_system.indexing import build_book_artifacts

    chapters = [
        {
            "chapter": 1,
            "title": "Chapter 1",
            "text": "韩立和张铁。",
            "paragraphs": ["韩立和张铁。"],
        },
        {
            "chapter": 2,
            "title": "Chapter 2",
            "text": "韩立再次出现。",
            "paragraphs": ["韩立再次出现。"],
        },
    ]

    artifacts = build_book_artifacts(chapters)
    registry = artifacts["character_registry"]

    # All entries should have canonical_name
    for entry in registry:
        assert "canonical_name" in entry
        assert "aliases" in entry
        assert "frequency" in entry
        assert "chapter_span" in entry


def test_character_registry_is_reproducible():
    """Character registry should produce stable results for same input."""
    from novel_system.indexing import build_book_artifacts

    chapters = [
        {
            "chapter": 1,
            "title": "Chapter 1",
            "text": "韩立和张铁一起出现。",
            "paragraphs": ["韩立和张铁一起出现。"],
        },
        {
            "chapter": 2,
            "title": "Chapter 2",
            "text": "韩立再次出现。张铁也在。",
            "paragraphs": ["韩立再次出现。张铁也在。"],
        },
    ]

    # Run twice with same input
    artifacts1 = build_book_artifacts(chapters)
    artifacts2 = build_book_artifacts(chapters)

    registry1 = artifacts1["character_registry"]
    registry2 = artifacts2["character_registry"]

    # Results should be identical
    assert len(registry1) == len(registry2)
    names1 = {r["canonical_name"] for r in registry1}
    names2 = {r["canonical_name"] for r in registry2}
    assert names1 == names2
