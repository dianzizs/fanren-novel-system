"""Generate GraphRAG settings.yaml for novel analysis."""

from __future__ import annotations

import logging
import os
from pathlib import Path

import yaml

from .paths import graphrag_settings_path, graphrag_prompts_dir
from ..config import AppConfig

logger = logging.getLogger(__name__)

ENTITY_TYPES = [
    "person",
    "organization",
    "location",
    "event",
    "item",
    "technique",
    "rule",
]


class GraphRAGSettingsBuilder:
    """Generate per-book GraphRAG settings.yaml."""

    def __init__(self, config: AppConfig) -> None:
        self._config = config

    def build(self, book_id: str) -> Path:
        api_key = self._config.graphrag_api_key or os.getenv("MINIMAX_API_KEY", "")
        if self._config.mimo_api_key:
            model_provider = "anthropic"
            model = self._config.mimo_chat_model
            api_base = self._config.mimo_base_url
            api_key_val = self._config.mimo_api_key
        else:
            model_provider = "openai"
            model = self._config.graphrag_chat_model
            api_base = self._config.graphrag_chat_api_base
            api_key_val = api_key

        settings = {
            "input": {"base_dir": "./input"},
            "output": {"base_dir": "./output"},
            "cache": {"base_dir": "./cache"},
            "reporting": {"base_dir": "./logs"},
            "completion_models": {
                "default_completion_model": {
                    "model_provider": model_provider,
                    "model": model,
                    "api_base": api_base,
                    "api_key": api_key_val,
                    "auth_method": "api_key",
                    "rate_limit": {
                        "type": "sliding_window",
                        "requests_per_period": 30,
                        "period_in_seconds": 60,
                    },
                }
            },
            "embedding_models": {
                "default_embedding_model": {
                    "model_provider": "openai",
                    "model": self._config.graphrag_embedding_model,
                    "api_base": self._config.graphrag_embedding_api_base,
                    "api_key": "EMPTY",
                    "auth_method": "api_key",
                }
            },
            "extract_graph": {
                "entity_types": ENTITY_TYPES,
            },
            "extract_claims": {
                "enabled": self._config.graphrag_enable_claims,
            },
            "embed_text": {
                "enabled": True,
            },
        }

        settings_path = graphrag_settings_path(self._config, book_id)
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        with open(settings_path, "w", encoding="utf-8") as f:
            yaml.dump(settings, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

        logger.info("Generated settings.yaml for %s at %s", book_id, settings_path)
        return settings_path
