"""Tests for MiniMaxClient fallback routing (MiniMax -> Mimo)."""
from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock, call

from novel_system.llm import MiniMaxClient


def _config(minimax_key="mm-key", mimo_key="mimo-key"):
    cfg = MagicMock()
    cfg.minimax_api_key = minimax_key
    cfg.minimax_base_url = "https://api.minimax.chat/v1"
    cfg.minimax_chat_model = "MiniMax-m2.7-HighSpeed"
    cfg.mimo_api_key = mimo_key
    cfg.mimo_base_url = "https://mimo.example.com"
    cfg.mimo_chat_model = "mimo-v2.5"
    return cfg


@patch("novel_system.llm.requests.post")
def test_minimax_success_no_fallback(mock_post):
    """Happy path: MiniMax returns 200, Mimo is never called."""
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {
        "choices": [{"message": {"content": "MiniMax output"}}],
        "usage": {"prompt_tokens": 5, "completion_tokens": 5, "total_tokens": 10},
    }
    mock_post.return_value = resp

    client = MiniMaxClient(_config())
    res = client.chat([{"role": "user", "content": "hi"}])

    assert res.content == "MiniMax output"
    assert mock_post.call_count == 1
    assert "chat/completions" in mock_post.call_args[0][0]


@patch("novel_system.llm.requests.post")
@patch("novel_system.llm.time.sleep")
def test_minimax_429_falls_back_to_mimo(mock_sleep, mock_post):
    """MiniMax returns 429 on all retries -> fallback to Mimo."""
    minimax_resp = MagicMock()
    minimax_resp.status_code = 429

    mimo_resp = MagicMock()
    mimo_resp.status_code = 200
    mimo_resp.json.return_value = {
        "content": [{"type": "text", "text": "Mimo output"}],
        "usage": {"input_tokens": 10, "output_tokens": 10, "cache_read_input_tokens": 0},
    }

    # MiniMax will be retried MAX_RETRIES+1 times, then fallback kicks in
    mock_post.side_effect = [minimax_resp] * (4) + [mimo_resp]  # 3 retries + 1 attempt = 4 minimax calls

    client = MiniMaxClient(_config())
    res = client.chat([{"role": "user", "content": "hi"}])

    assert res.content == "Mimo output"
    # Verify the last call went to Mimo endpoint
    last_url = mock_post.call_args_list[-1][0][0]
    assert "mimo.example.com" in last_url


@patch("novel_system.llm.requests.post")
def test_minimax_unconfigured_routes_to_mimo(mock_post):
    """If MiniMax key is empty, routes directly to Mimo without any MiniMax call."""
    mimo_resp = MagicMock()
    mimo_resp.status_code = 200
    mimo_resp.json.return_value = {
        "content": [{"type": "text", "text": "Mimo direct"}],
        "usage": {"input_tokens": 5, "output_tokens": 5, "cache_read_input_tokens": 0},
    }
    mock_post.return_value = mimo_resp

    client = MiniMaxClient(_config(minimax_key=""))
    res = client.chat([{"role": "user", "content": "hi"}])

    assert res.content == "Mimo direct"
    assert mock_post.call_count == 1
    assert "mimo.example.com" in mock_post.call_args[0][0]


def test_neither_configured_raises():
    """If both keys are empty, RuntimeError is raised."""
    client = MiniMaxClient(_config(minimax_key="", mimo_key=""))
    with pytest.raises(RuntimeError):
        client.chat([{"role": "user", "content": "hi"}])


@patch("novel_system.llm.requests.post")
def test_enabled_true_when_either_configured(mock_post):
    assert MiniMaxClient(_config(minimax_key="k", mimo_key="")).enabled
    assert MiniMaxClient(_config(minimax_key="", mimo_key="k")).enabled
    assert not MiniMaxClient(_config(minimax_key="", mimo_key="")).enabled
