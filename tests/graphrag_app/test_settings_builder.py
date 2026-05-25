"""Test GraphRAG settings builder."""

import yaml

from novel_system.graphrag_app.settings_builder import GraphRAGSettingsBuilder


def test_settings_builder_creates_valid_yaml(test_config):
    config = test_config
    builder = GraphRAGSettingsBuilder(config)
    book_id = "test-book-settings"

    path = builder.build(book_id)
    assert path.exists()

    content = path.read_text(encoding="utf-8")
    assert "completion_models:" in content
    assert "embedding_models:" in content
    assert "extract_graph:" in content

    # Cleanup
    import shutil
    shutil.rmtree(path.parent, ignore_errors=True)


def test_settings_builder_yaml_contains_expected_fields(test_config):
    builder = GraphRAGSettingsBuilder(test_config)

    path = builder.build("test-book-settings-strong")
    settings = yaml.safe_load(path.read_text(encoding="utf-8"))

    assert settings["input"]["base_dir"] == "./input"
    assert settings["output"]["base_dir"] == "./output"
    assert settings["completion_models"]["default_completion_model"]["model"] == test_config.graphrag_chat_model
    assert settings["completion_models"]["default_completion_model"]["api_base"] == test_config.graphrag_chat_api_base
    assert settings["embedding_models"]["default_embedding_model"]["model"] == test_config.graphrag_embedding_model
    assert settings["embedding_models"]["default_embedding_model"]["api_key"] == "EMPTY"
    assert "person" in settings["extract_graph"]["entity_types"]
    assert settings["extract_claims"]["enabled"] is test_config.graphrag_enable_claims
