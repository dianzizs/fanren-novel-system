"""Tests for Mimo configuration loading."""
from __future__ import annotations

import os
from unittest.mock import patch

from novel_system.config import AppConfig


def test_mimo_config_defaults():
    """Mimo config uses expected defaults when no env vars are set."""
    env_overrides = {
        "MIMO_API_KEY": "",
        "MIMO_BASE_URL": "",
        "MIMO_CHAT_MODEL": "",
        "ANTHROPIC_AUTH_TOKEN": "",
        "ANTHROPIC_BASE_URL": "",
    }
    with patch.dict(os.environ, env_overrides):
        config = AppConfig.load()
        assert config.mimo_base_url == "https://token-plan-cn.xiaomimimo.com/anthropic"
        assert config.mimo_chat_model == "mimo-v2.5"
        assert config.mimo_api_key == ""


def test_mimo_config_from_env():
    """Mimo config reads from MIMO_* env vars."""
    env = {
        "MIMO_API_KEY": "mimo-key-123",
        "MIMO_BASE_URL": "https://mimo.example.com",
        "MIMO_CHAT_MODEL": "custom-mimo",
    }
    with patch.dict(os.environ, env):
        config = AppConfig.load()
        assert config.mimo_api_key == "mimo-key-123"
        assert config.mimo_base_url == "https://mimo.example.com"
        assert config.mimo_chat_model == "custom-mimo"


def test_mimo_config_anthropic_fallback():
    """Mimo config falls back to ANTHROPIC_* env vars when MIMO_* are absent."""
    env = {
        "MIMO_API_KEY": "",
        "MIMO_BASE_URL": "",
        "ANTHROPIC_AUTH_TOKEN": "anthropic-key-123",
        "ANTHROPIC_BASE_URL": "https://anthropic.example.com",
    }
    with patch.dict(os.environ, env):
        config = AppConfig.load()
        assert config.mimo_api_key == "anthropic-key-123"
        assert config.mimo_base_url == "https://anthropic.example.com"


def test_mimo_trailing_slash_stripped():
    """Trailing slash is stripped from mimo_base_url."""
    with patch.dict(os.environ, {"MIMO_BASE_URL": "https://mimo.example.com/"}):
        config = AppConfig.load()
        assert not config.mimo_base_url.endswith("/")
