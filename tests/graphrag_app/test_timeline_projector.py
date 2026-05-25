"""Test GraphRAG timeline projector."""

import json

import pandas as pd

from novel_system.graphrag_app.timeline_projector import GraphRAGTimelineProjector
from novel_system.graphrag_app.paths import graphrag_output_dir


def test_timeline_projector_prefers_covariates(test_config):
    output_dir = graphrag_output_dir(test_config, "book-timeline-covariates")
    output_dir.mkdir(parents=True)
    pd.DataFrame(
        [{"id": "claim-1", "type": "event", "subject_id": "韩立", "description": "韩立拜入七玄门"}]
    ).to_parquet(output_dir / "covariates.parquet", index=False)
    pd.DataFrame([{"id": "tu-1", "text": "x" * 80}]).to_parquet(output_dir / "text_units.parquet", index=False)
    pd.DataFrame([{"id": "e1", "title": "韩立"}]).to_parquet(output_dir / "entities.parquet", index=False)

    path = GraphRAGTimelineProjector(test_config).build("book-timeline-covariates")

    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["event_count"] == 1
    assert data["events"][0]["id"] == "claim-1"
    assert data["events"][0]["description"] == "韩立拜入七玄门"
    assert "text" not in data["events"][0]


def test_timeline_projector_falls_back_to_text_units(test_config):
    output_dir = graphrag_output_dir(test_config, "book-timeline-text-units")
    output_dir.mkdir(parents=True)
    long_text = "韩立在七玄门经历了一次重要考验。" * 5
    pd.DataFrame(
        [
            {"id": "short", "text": "太短"},
            {"id": "tu-1", "text": long_text},
        ]
    ).to_parquet(output_dir / "text_units.parquet", index=False)
    pd.DataFrame([{"id": "e1", "title": "韩立"}]).to_parquet(output_dir / "entities.parquet", index=False)

    path = GraphRAGTimelineProjector(test_config).build("book-timeline-text-units")

    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["event_count"] == 1
    assert data["events"][0]["id"] == "tu-1"
    assert data["events"][0]["source"] == "text_unit"
    assert data["events"][0]["text"] == long_text[:200]
