"""Project GraphRAG entities/relationships to front-end graph view."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from .paths import derived_dir
from .table_loader import GraphRAGTableLoader
from ..config import AppConfig

logger = logging.getLogger(__name__)


def _row_value(row, *keys: str) -> str:
    for key in keys:
        value = row.get(key, "")
        if value is not None and str(value) and str(value) != "nan":
            return str(value)
    return ""


class GraphRAGGraphProjector:
    """Generate front-end interactive graph from GraphRAG entities and relationships."""

    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._loader = GraphRAGTableLoader(config)

    def build(self, book_id: str) -> Path | None:
        try:
            entities_df = self._loader.load(book_id, "entities")
            relationships_df = self._loader.load(book_id, "relationships")
        except FileNotFoundError:
            logger.warning("GraphRAG parquet tables not found for %s, skipping graph build", book_id)
            return None

        nodes: list[dict] = []
        edges: list[dict] = []
        entity_lookup: dict[str, str] = {}

        for _, row in entities_df.iterrows():
            label = _row_value(row, "title", "name", "id")
            if not label:
                continue
            node_id = f"entity::{label}"
            nodes.append({
                "id": node_id,
                "label": label,
                "type": _row_value(row, "type") or "unknown",
                "description": _row_value(row, "description")[:200],
                "degree": int(row.get("degree", 0)) if "degree" in row else 0,
            })
            for key in ("id", "title", "name"):
                value = _row_value(row, key)
                if value:
                    entity_lookup[value] = node_id

        for _, row in relationships_df.iterrows():
            source = str(row.get("source", ""))
            target = str(row.get("target", ""))
            s_id = entity_lookup.get(source)
            t_id = entity_lookup.get(target)
            if s_id and t_id:
                edges.append({
                    "source": s_id,
                    "target": t_id,
                    "weight": float(row.get("weight", 1.0)),
                    "description": _row_value(row, "description")[:200],
                })

        graph_view = {
            "nodes": nodes,
            "edges": edges,
            "node_count": len(nodes),
            "edge_count": len(edges),
        }

        output_path = derived_dir(self._config, book_id) / "graph_view.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(graph_view, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("Built graph_view.json for %s: %d nodes, %d edges", book_id, len(nodes), len(edges))
        return output_path

    def get_interactive_graph(
        self, book_id: str, center: str | None = None, limit: int = 18
    ) -> dict:
        derived = derived_dir(self._config, book_id) / "graph_view.json"
        if not derived.exists():
            result = self.build(book_id)
            if result is None:
                return {"nodes": [], "edges": [], "available_characters": [], "center": None, "stats": {"character_count": 0, "event_count": 0, "edge_count": 0}}
        data = json.loads(derived.read_text(encoding="utf-8"))

        nodes = data.get("nodes", [])
        edges = data.get("edges", [])

        if center:
            center_id = next(
                (
                    n["id"]
                    for n in nodes
                    if n.get("id") == f"entity::{center}" or n.get("label") == center
                ),
                f"entity::{center}",
            )
            connected_ids = {
                e["target"] for e in edges if e["source"] == center_id
            } | {
                e["source"] for e in edges if e["target"] == center_id
            }
            connected_ids.add(center_id)
            nodes = [n for n in nodes if n["id"] in connected_ids][:limit]
            node_ids = {n["id"] for n in nodes}
            edges = [e for e in edges if e["source"] in node_ids and e["target"] in node_ids][:limit * 2]
        else:
            nodes = nodes[:limit]
            node_ids = {n["id"] for n in nodes}
            edges = [e for e in edges if e["source"] in node_ids and e["target"] in node_ids][:limit * 2]

        available = [n["label"] for n in nodes if n["label"]]

        return {
            "nodes": nodes,
            "edges": edges,
            "available_characters": available,
            "center": center,
            "stats": {
                "character_count": len(nodes),
                "event_count": 0,
                "edge_count": len(edges),
            },
        }
