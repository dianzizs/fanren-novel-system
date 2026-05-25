"""Debug output for GraphRAG tables, context, and traces."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from .paths import derived_dir
from .table_loader import GraphRAGTableLoader
from ..config import AppConfig

logger = logging.getLogger(__name__)


class GraphRAGDebugDump:
    """Dump GraphRAG internal state for debugging."""

    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._loader = GraphRAGTableLoader(config)

    def dump_tables(self, book_id: str) -> Path:
        tables = self._loader.load_all(book_id)
        debug_dir = derived_dir(self._config, book_id) / "debug_samples"
        debug_dir.mkdir(parents=True, exist_ok=True)

        for name, df in tables.items():
            sample = df.head(5).to_dict(orient="records")
            (debug_dir / f"{name}_sample.json").write_text(
                json.dumps(sample, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )

        sizes = {name: len(df) for name, df in tables.items()}
        (debug_dir / "table_sizes.json").write_text(
            json.dumps(sizes, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info("Dumped table debug info for %s to %s", book_id, debug_dir)
        return debug_dir

    def dump_context(self, book_id: str, context_data: Any) -> Path:
        debug_dir = derived_dir(self._config, book_id) / "debug_samples"
        debug_dir.mkdir(parents=True, exist_ok=True)
        path = debug_dir / "last_context.json"
        path.write_text(
            json.dumps(context_data, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        return path
