"""Validate GraphRAG output tables for completeness."""

from __future__ import annotations

import logging
from pathlib import Path

from .paths import graphrag_output_dir
from ..config import AppConfig

logger = logging.getLogger(__name__)

REQUIRED_TABLES = ["entities", "relationships", "communities", "community_reports", "text_units", "documents"]


class GraphRAGTableValidator:
    """Check that GraphRAG indexing produced all required output tables."""

    def __init__(self, config: AppConfig) -> None:
        self._config = config

    def validate(self, book_id: str) -> dict:
        output_dir = graphrag_output_dir(self._config, book_id)
        found: list[str] = []
        missing: list[str] = []
        for table_name in REQUIRED_TABLES:
            matches = list(output_dir.glob(f"*{table_name}*.parquet"))
            if matches:
                found.append(table_name)
            else:
                missing.append(table_name)

        if missing:
            logger.warning("Missing GraphRAG output tables for %s: %s", book_id, missing)

        covariates_found = bool(list(output_dir.glob("*covariate*.parquet")))
        return {
            "all_required_present": len(missing) == 0,
            "found": found,
            "missing": missing,
            "covariates_present": covariates_found,
            "total_parquet_files": len(list(output_dir.glob("*.parquet"))),
        }
