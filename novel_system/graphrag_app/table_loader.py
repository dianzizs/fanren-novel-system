"""Load GraphRAG output parquet tables with filename alias support."""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from .paths import graphrag_output_dir
from ..config import AppConfig

logger = logging.getLogger(__name__)

TABLE_ALIASES: dict[str, list[str]] = {
    "documents": ["documents.parquet", "create_final_documents.parquet"],
    "text_units": ["text_units.parquet", "create_final_text_units.parquet"],
    "entities": ["entities.parquet", "create_final_entities.parquet"],
    "relationships": ["relationships.parquet", "create_final_relationships.parquet"],
    "communities": ["communities.parquet", "create_final_communities.parquet"],
    "community_reports": ["community_reports.parquet", "create_final_community_reports.parquet"],
    "covariates": ["covariates.parquet", "create_final_covariates.parquet"],
}


class GraphRAGTableLoader:
    """Load GraphRAG output parquet tables with filename alias fallback."""

    def __init__(self, config: AppConfig) -> None:
        self._config = config

    def _resolve_path(self, book_id: str, table_name: str) -> Path | None:
        output_dir = graphrag_output_dir(self._config, book_id)
        aliases = TABLE_ALIASES.get(table_name, [f"{table_name}.parquet"])
        for alias in aliases:
            candidate = output_dir / alias
            if candidate.exists():
                return candidate
        # Fallback: try glob match
        for pattern in [f"*{table_name}*.parquet", f"*{table_name.replace('_', '')}*.parquet"]:
            matches = list(output_dir.glob(pattern))
            if matches:
                return matches[0]
        return None

    def load(self, book_id: str, table_name: str) -> pd.DataFrame:
        path = self._resolve_path(book_id, table_name)
        if path is None:
            raise FileNotFoundError(f"Table {table_name} not found for {book_id}")
        df = pd.read_parquet(path)
        logger.debug("Loaded %s: %d rows from %s", table_name, len(df), path.name)
        return df

    def load_all(self, book_id: str) -> dict[str, pd.DataFrame]:
        result: dict[str, pd.DataFrame] = {}
        for name in TABLE_ALIASES:
            try:
                result[name] = self.load(book_id, name)
            except FileNotFoundError:
                logger.debug("Table %s not available for %s", name, book_id)
        return result

    def exists(self, book_id: str, table_name: str) -> bool:
        return self._resolve_path(book_id, table_name) is not None

    def table_sizes(self, book_id: str) -> dict[str, int]:
        sizes: dict[str, int] = {}
        for name in TABLE_ALIASES:
            try:
                df = self.load(book_id, name)
                sizes[name] = len(df)
            except FileNotFoundError:
                sizes[name] = 0
        return sizes
