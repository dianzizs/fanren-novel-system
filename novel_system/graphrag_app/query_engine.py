"""GraphRAG query engine - unified entry point for all search modes."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

try:
    from graphrag.api.query import local_search, global_search, drift_search, basic_search
    from graphrag.config.load_config import load_config
    _GRAPHRAG_AVAILABLE = True
except ImportError:
    _GRAPHRAG_AVAILABLE = False

from .paths import graphrag_settings_path
from .table_loader import GraphRAGTableLoader
from .query_router import GraphRAGQueryRouter
from ..config import AppConfig

logger = logging.getLogger(__name__)


@dataclass
class GraphRAGQueryResult:
    response: str
    context_data: Any
    mode: str
    matched_entities: list[str] = field(default_factory=list)
    used_community_reports: list[str] = field(default_factory=list)
    used_text_units: list[str] = field(default_factory=list)


class GraphRAGQueryEngine:
    """Unified async query engine wrapping GraphRAG Python API."""

    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._table_loader = GraphRAGTableLoader(config)
        self._router = GraphRAGQueryRouter()

    async def search(
        self,
        book_id: str,
        query: str,
        mode: str = "auto",
        conversation_history: list[dict] | None = None,
        **kwargs,
    ) -> GraphRAGQueryResult:
        if not _GRAPHRAG_AVAILABLE:
            return GraphRAGQueryResult(
                response="GraphRAG is not installed. Please run: pip install -e D:\\pythonProject\\graphrag\\packages\\graphrag",
                context_data={},
                mode=mode,
            )
        settings_path = graphrag_settings_path(self._config, book_id)
        graph_config = load_config(root_dir=str(settings_path.parent))

        mode = self._router.route(query, requested_mode=None if mode == "auto" else mode)

        try:
            if mode == "local":
                response, context = await self._local_search(graph_config, book_id, query)
            elif mode == "global":
                response, context = await self._global_search(graph_config, book_id, query)
            elif mode == "drift":
                response, context = await self._drift_search(graph_config, book_id, query)
            elif mode == "basic":
                response, context = await self._basic_search(graph_config, book_id, query)
            else:
                response, context = await self._local_search(graph_config, book_id, query)
                mode = "local"
        except Exception as e:
            logger.exception("GraphRAG %s search failed for %s: %s", mode, book_id, e)
            return GraphRAGQueryResult(
                response=f"查询失败：{e}",
                context_data={},
                mode=mode,
            )

        matched_entities = self._extract_entity_names(context)
        used_reports = self._extract_report_ids(context)
        used_units = self._extract_text_unit_ids(context)

        return GraphRAGQueryResult(
            response=str(response),
            context_data=context,
            mode=mode,
            matched_entities=matched_entities,
            used_community_reports=used_reports,
            used_text_units=used_units,
        )

    async def _local_search(self, graph_config, book_id: str, query: str):
        entities = self._table_loader.load(book_id, "entities")
        communities = self._table_loader.load(book_id, "communities")
        community_reports = self._table_loader.load(book_id, "community_reports")
        text_units = self._table_loader.load(book_id, "text_units")
        relationships = self._table_loader.load(book_id, "relationships")
        try:
            covariates = self._table_loader.load(book_id, "covariates")
        except FileNotFoundError:
            covariates = None

        return await local_search(
            config=graph_config,
            entities=entities,
            communities=communities,
            community_reports=community_reports,
            text_units=text_units,
            relationships=relationships,
            covariates=covariates,
            community_level=2,
            response_type="Multiple Paragraphs",
            query=query,
        )

    async def _global_search(self, graph_config, book_id: str, query: str):
        entities = self._table_loader.load(book_id, "entities")
        communities = self._table_loader.load(book_id, "communities")
        community_reports = self._table_loader.load(book_id, "community_reports")

        return await global_search(
            config=graph_config,
            entities=entities,
            communities=communities,
            community_reports=community_reports,
            community_level=None,
            dynamic_community_selection=True,
            response_type="Multiple Paragraphs",
            query=query,
        )

    async def _drift_search(self, graph_config, book_id: str, query: str):
        entities = self._table_loader.load(book_id, "entities")
        communities = self._table_loader.load(book_id, "communities")
        community_reports = self._table_loader.load(book_id, "community_reports")
        text_units = self._table_loader.load(book_id, "text_units")
        relationships = self._table_loader.load(book_id, "relationships")

        return await drift_search(
            config=graph_config,
            entities=entities,
            communities=communities,
            community_reports=community_reports,
            text_units=text_units,
            relationships=relationships,
            community_level=2,
            response_type="Multiple Paragraphs",
            query=query,
        )

    async def _basic_search(self, graph_config, book_id: str, query: str):
        text_units = self._table_loader.load(book_id, "text_units")

        return await basic_search(
            config=graph_config,
            text_units=text_units,
            response_type="Multiple Paragraphs",
            query=query,
        )

    @staticmethod
    def _extract_entity_names(context_data: Any) -> list[str]:
        if isinstance(context_data, dict):
            entities = context_data.get("entities", [])
            if hasattr(entities, "list"):
                entities = entities.list()
            if isinstance(entities, list):
                return [e.get("title", e.get("name", str(e))) for e in entities[:10] if isinstance(e, dict)]
        return []

    @staticmethod
    def _extract_report_ids(context_data: Any) -> list[str]:
        if isinstance(context_data, dict):
            reports = context_data.get("reports", [])
            if isinstance(reports, list):
                return [r.get("id", str(r)) for r in reports[:5] if isinstance(r, dict)]
        return []

    @staticmethod
    def _extract_text_unit_ids(context_data: Any) -> list[str]:
        if isinstance(context_data, dict):
            units = context_data.get("text_units", [])
            if isinstance(units, list):
                return [u.get("id", str(u)) for u in units[:5] if isinstance(u, dict)]
        return []
