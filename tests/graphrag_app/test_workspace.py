"""Test GraphRAG workspace lifecycle."""

import tempfile
from pathlib import Path

from novel_system.config import AppConfig
from novel_system.graphrag_app.workspace import GraphRAGWorkspace


def test_workspace_prepare_and_status():
    config = AppConfig.load()
    workspace = GraphRAGWorkspace(config)
    book_id = "test-book-workspace"
    source = Path(tempfile.mkdtemp()) / "test.txt"
    source.write_text("测试内容", encoding="utf-8")

    workspace.prepare(book_id, source)
    assert workspace.exists(book_id)

    status = workspace.status(book_id)
    assert status["workspace_exists"]
    assert not status["has_settings"]

    workspace.clear(book_id)


def test_workspace_clear():
    config = AppConfig.load()
    workspace = GraphRAGWorkspace(config)
    book_id = "test-book-clear"
    source = Path(tempfile.mkdtemp()) / "test.txt"
    source.write_text("测试", encoding="utf-8")

    workspace.prepare(book_id, source)
    workspace.clear(book_id)
    assert not workspace.exists(book_id)
