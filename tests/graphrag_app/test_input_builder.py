"""Test GraphRAG input builder."""

from novel_system.graphrag_app.input_builder import GraphRAGInputBuilder
from novel_system.graphrag_app.paths import graphrag_input_dir


def test_build_from_txt_creates_chapter_files(test_config, tmp_path):
    config = test_config
    builder = GraphRAGInputBuilder(config)
    book_id = "test-book-input"
    source = tmp_path / "source.txt"
    source.write_text(
        "第1章 开始\n\n这是第一章内容。\n\n第2章 继续\n\n这是第二章内容。",
        encoding="utf-8",
    )

    result = builder.build_from_txt(book_id, source)
    assert result["chapter_count"] > 0
    assert result["input_files"] > 0

    input_dir = graphrag_input_dir(config, book_id)
    files = list(input_dir.glob("*.txt"))
    assert len(files) == result["chapter_count"]

    # Cleanup
    import shutil
    shutil.rmtree(input_dir.parent, ignore_errors=True)
    source.unlink(missing_ok=True)


def test_build_from_txt_writes_chapter_metadata_and_total_chars(test_config, tmp_path):
    builder = GraphRAGInputBuilder(test_config)
    book_id = "test-book-input-strong"
    source = tmp_path / "novel.txt"
    chapter_one = "这是第一章内容。"
    chapter_two = "这是第二章内容。"
    source.write_text(
        f"第一章 开始\n\n{chapter_one}\n\n第二章 继续\n\n{chapter_two}",
        encoding="utf-8",
    )

    result = builder.build_from_txt(book_id, source)

    assert result == {
        "chapter_count": 2,
        "input_files": 2,
        "total_chars": len(chapter_one) + len(chapter_two),
    }
    input_dir = graphrag_input_dir(test_config, book_id)
    assert sorted(path.name for path in input_dir.glob("*.txt")) == [
        "chapter_0001.txt",
        "chapter_0002.txt",
    ]
    first = (input_dir / "chapter_0001.txt").read_text(encoding="utf-8")
    assert "# book_id: test-book-input-strong" in first
    assert "# chapter_index: 1" in first
    assert "# chapter_title: 开始" in first
    assert first.endswith(f"{chapter_one}\n")


def test_build_from_txt_limits_chapters(test_config, tmp_path):
    import os
    config = test_config
    builder = GraphRAGInputBuilder(config)
    book_id = "test-book-input-limit"
    source = tmp_path / "source.txt"
    source.write_text(
        "第1章 开始\n\n这是第一章内容。\n\n第2章 继续\n\n这是第二章内容。",
        encoding="utf-8",
    )

    os.environ["GRAPHRAG_MAX_CHAPTERS"] = "1"
    try:
        result = builder.build_from_txt(book_id, source)
        assert result["chapter_count"] == 1
        assert result["input_files"] == 1
        input_dir = graphrag_input_dir(config, book_id)
        files = list(input_dir.glob("*.txt"))
        assert len(files) == 1
        assert files[0].name == "chapter_0001.txt"
    finally:
        os.environ.pop("GRAPHRAG_MAX_CHAPTERS", None)
        import shutil
        shutil.rmtree(input_dir.parent, ignore_errors=True)
        source.unlink(missing_ok=True)
