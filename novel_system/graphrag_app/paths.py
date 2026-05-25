"""GraphRAG workspace path management."""

from __future__ import annotations

from pathlib import Path

from ..config import AppConfig


def book_root(config: AppConfig, book_id: str) -> Path:
    return config.books_dir / book_id


def graphrag_root(config: AppConfig, book_id: str) -> Path:
    return book_root(config, book_id) / "graphrag"


def graphrag_input_dir(config: AppConfig, book_id: str) -> Path:
    return graphrag_root(config, book_id) / "input"


def graphrag_output_dir(config: AppConfig, book_id: str) -> Path:
    return graphrag_root(config, book_id) / "output"


def graphrag_settings_path(config: AppConfig, book_id: str) -> Path:
    return graphrag_root(config, book_id) / "settings.yaml"


def graphrag_prompts_dir(config: AppConfig, book_id: str) -> Path:
    return graphrag_root(config, book_id) / "prompts"


def derived_dir(config: AppConfig, book_id: str) -> Path:
    return book_root(config, book_id) / "derived"
