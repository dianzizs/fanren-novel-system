"""GraphRAG workspace lifecycle management."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from .paths import graphrag_root, graphrag_input_dir, graphrag_output_dir
from ..config import AppConfig

logger = logging.getLogger(__name__)


class GraphRAGWorkspace:
    """Manage per-book GraphRAG workspace directories."""

    def __init__(self, config: AppConfig) -> None:
        self._config = config

    def prepare(self, book_id: str, source_path: Path) -> None:
        root = graphrag_root(self._config, book_id)
        root.mkdir(parents=True, exist_ok=True)
        graphrag_input_dir(self._config, book_id).mkdir(parents=True, exist_ok=True)
        graphrag_output_dir(self._config, book_id).mkdir(parents=True, exist_ok=True)
        (root / "cache").mkdir(exist_ok=True)
        (root / "logs").mkdir(exist_ok=True)
        from .paths import graphrag_prompts_dir
        graphrag_prompts_dir(self._config, book_id).mkdir(parents=True, exist_ok=True)
        logger.info("Prepared GraphRAG workspace for %s at %s", book_id, root)

    def exists(self, book_id: str) -> bool:
        return graphrag_root(self._config, book_id).exists()

    def clear(self, book_id: str) -> None:
        root = graphrag_root(self._config, book_id)
        if root.exists():
            shutil.rmtree(root)
            logger.info("Cleared GraphRAG workspace for %s", book_id)

    def status(self, book_id: str) -> dict:
        root = graphrag_root(self._config, book_id)
        has_settings = (root / "settings.yaml").exists()
        input_files = list(graphrag_input_dir(self._config, book_id).glob("*.txt")) if root.exists() else []
        output_files = list(graphrag_output_dir(self._config, book_id).glob("*.parquet")) if root.exists() else []
        return {
            "workspace_exists": root.exists(),
            "has_settings": has_settings,
            "input_file_count": len(input_files),
            "output_parquet_count": len(output_files),
            "output_parquet_names": [f.name for f in output_files],
        }
