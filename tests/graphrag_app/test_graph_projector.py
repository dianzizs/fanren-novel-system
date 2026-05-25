"""Test GraphRAG graph projector."""

import json

import pandas as pd

from novel_system.graphrag_app.graph_projector import GraphRAGGraphProjector
from novel_system.graphrag_app.paths import graphrag_output_dir


def test_graph_projector_builds_nodes_edges_and_skips_dangling_edges(test_config):
    output_dir = graphrag_output_dir(test_config, "book-graph")
    output_dir.mkdir(parents=True)
    pd.DataFrame(
        [
            {"id": "e1", "title": "韩立", "type": "person", "description": "主角", "degree": 3},
            {"id": "e2", "title": "墨大夫", "type": "person", "description": "医生", "degree": 1},
        ]
    ).to_parquet(output_dir / "entities.parquet", index=False)
    pd.DataFrame(
        [
            {"source": "韩立", "target": "墨大夫", "weight": 2.5, "description": "师徒"},
            {"source": "韩立", "target": "不存在的人", "weight": 1.0, "description": "坏边"},
        ]
    ).to_parquet(output_dir / "relationships.parquet", index=False)

    path = GraphRAGGraphProjector(test_config).build("book-graph")

    data = json.loads(path.read_text(encoding="utf-8"))
    node_ids = {node["id"] for node in data["nodes"]} | {f"entity::{node['label']}" for node in data["nodes"]}
    assert data["node_count"] == 2
    assert {node["label"] for node in data["nodes"]} == {"韩立", "墨大夫"}
    assert data["edges"] == [
        {
            "source": "entity::韩立",
            "target": "entity::墨大夫",
            "weight": 2.5,
            "description": "师徒",
        }
    ]
    assert all(edge["source"] in node_ids and edge["target"] in node_ids for edge in data["edges"])


def test_graph_projector_center_filters_connected_subgraph(test_config):
    output_dir = graphrag_output_dir(test_config, "book-centered")
    output_dir.mkdir(parents=True)
    pd.DataFrame(
        [
            {"id": "e1", "title": "韩立", "type": "person"},
            {"id": "e2", "title": "墨大夫", "type": "person"},
            {"id": "e3", "title": "张铁", "type": "person"},
        ]
    ).to_parquet(output_dir / "entities.parquet", index=False)
    pd.DataFrame(
        [
            {"source": "韩立", "target": "墨大夫", "weight": 1.0},
            {"source": "张铁", "target": "墨大夫", "weight": 1.0},
        ]
    ).to_parquet(output_dir / "relationships.parquet", index=False)

    graph = GraphRAGGraphProjector(test_config).get_interactive_graph("book-centered", center="韩立")

    assert {node["label"] for node in graph["nodes"]} == {"韩立", "墨大夫"}
    assert graph["edges"] == [{"source": "entity::韩立", "target": "entity::墨大夫", "weight": 1.0, "description": ""}]
    assert graph["center"] == "韩立"
