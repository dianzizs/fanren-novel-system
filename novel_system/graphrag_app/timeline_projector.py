"""Project GraphRAG covariates/text_units to timeline view."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pandas as pd

from .paths import derived_dir
from .table_loader import GraphRAGTableLoader
from ..config import AppConfig

logger = logging.getLogger(__name__)


class GraphRAGTimelineProjector:
    """Generate timeline view from GraphRAG covariates or text_units."""

    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._loader = GraphRAGTableLoader(config)

    def build(self, book_id: str) -> Path:
        events: list[dict] = []

        try:
            covariates_df = self._loader.load(book_id, "covariates")
            events = self._from_covariates(covariates_df)
            logger.info("Built timeline from covariates for %s: %d events", book_id, len(events))
        except FileNotFoundError:
            try:
                text_units_df = self._loader.load(book_id, "text_units")
                entities_df = self._loader.load(book_id, "entities")
                events = self._from_text_units(text_units_df, entities_df)
                logger.info("Built timeline from text_units for %s: %d events", book_id, len(events))
            except FileNotFoundError:
                logger.warning("No covariates or text_units available for timeline in %s", book_id)

        timeline_view = {"events": events, "event_count": len(events)}

        output_path = derived_dir(self._config, book_id) / "timeline_view.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(timeline_view, ensure_ascii=False, indent=2), encoding="utf-8")
        return output_path

    @staticmethod
    def _from_covariates(df: pd.DataFrame) -> list[dict]:
        events: list[dict] = []
        for _, row in df.iterrows():
            events.append({
                "id": str(row.get("id", "")),
                "type": str(row.get("type", "claim")),
                "subject": str(row.get("subject_id", "")),
                "description": str(row.get("description", row.get("text", ""))),
                "chapter": 0,
            })
        return events[:500]

    @staticmethod
    def _from_text_units(text_units_df: pd.DataFrame, _entities_df: pd.DataFrame) -> list[dict]:
        events: list[dict] = []
        for _, row in text_units_df.iterrows():
            text = str(row.get("text", ""))
            if len(text) < 50:
                continue
            events.append({
                "id": str(row.get("id", "")),
                "text": text[:200],
                "chapter": 0,
                "source": "text_unit",
            })
        return events[:200]

    def get_timeline(self, book_id: str) -> list[dict]:
        derived = derived_dir(self._config, book_id) / "timeline_view.json"
        if not derived.exists():
            self.build(book_id)
        if not derived.exists():
            return []
        try:
            data = json.loads(derived.read_text(encoding="utf-8"))
            return data.get("events", [])
        except Exception:
            return []
