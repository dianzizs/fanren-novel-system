"""Test GraphRAG table loader with alias resolution."""

import pandas as pd
import pytest

from novel_system.graphrag_app.paths import graphrag_output_dir
from novel_system.graphrag_app.table_loader import TABLE_ALIASES, GraphRAGTableLoader


def test_table_aliases_have_required_keys():
    required = ["documents", "text_units", "entities", "relationships", "communities", "community_reports", "covariates"]
    for key in required:
        assert key in TABLE_ALIASES, f"Missing alias key: {key}"
        assert len(TABLE_ALIASES[key]) >= 1


def test_table_alias_names_match_pattern():
    for aliases in TABLE_ALIASES.values():
        for alias in aliases:
            assert alias.endswith(".parquet"), f"Alias should end with .parquet: {alias}"


def test_loader_reads_real_parquet_alias(test_config):
    output_dir = graphrag_output_dir(test_config, "book-alias")
    output_dir.mkdir(parents=True)
    expected = pd.DataFrame(
        [
            {"id": "e1", "title": "韩立"},
            {"id": "e2", "title": "墨大夫"},
        ]
    )
    expected.to_parquet(output_dir / "create_final_entities.parquet", index=False)

    loader = GraphRAGTableLoader(test_config)
    actual = loader.load("book-alias", "entities")

    assert actual.to_dict("records") == expected.to_dict("records")
    assert loader.exists("book-alias", "entities") is True


def test_loader_missing_table_raises_file_not_found(test_config):
    loader = GraphRAGTableLoader(test_config)

    with pytest.raises(FileNotFoundError, match="Table entities not found"):
        loader.load("missing-book", "entities")
