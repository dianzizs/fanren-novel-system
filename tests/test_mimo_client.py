"""Tests for MimoClient (Anthropic-compatible LLM client)."""
from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock

from novel_system.llm import MimoClient, LLMResponse


def _mimo_config(api_key="test-key"):
    cfg = MagicMock()
    cfg.mimo_api_key = api_key
    cfg.mimo_base_url = "https://test.mimo.com"
    cfg.mimo_chat_model = "mimo-v2.5"
    return cfg


def test_mimo_disabled_when_no_key():
    client = MimoClient(_mimo_config(api_key=""))
    assert not client.enabled
    with pytest.raises(RuntimeError, match="MIMO_API_KEY"):
        client.chat([{"role": "user", "content": "hello"}])


@patch("novel_system.llm.requests.post")
def test_mimo_chat_success(mock_post):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "content": [
            {"type": "thinking", "thinking": "let me think"},
            {"type": "text", "text": "Mimo response content"},
        ],
        "usage": {
            "input_tokens": 10,
            "output_tokens": 20,
            "cache_read_input_tokens": 5,
        },
    }
    mock_post.return_value = mock_resp

    client = MimoClient(_mimo_config())
    res = client.chat([{"role": "user", "content": "hello"}])

    assert res.content == "Mimo response content"
    assert res.usage["prompt_tokens"] == 15
    assert res.usage["completion_tokens"] == 20
    assert res.usage["total_tokens"] == 35


@patch("novel_system.llm.requests.post")
def test_mimo_system_message_extracted(mock_post):
    """System messages are extracted and sent as top-level 'system' param."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "content": [{"type": "text", "text": "ok"}],
        "usage": {"input_tokens": 5, "output_tokens": 5, "cache_read_input_tokens": 0},
    }
    mock_post.return_value = mock_resp

    msgs = [
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": "hi"},
    ]
    client = MimoClient(_mimo_config())
    client.chat(msgs)

    call_json = mock_post.call_args[1]["json"]
    assert call_json["system"] == "You are helpful."
    assert all(m["role"] != "system" for m in call_json["messages"])


@patch("novel_system.llm.requests.post")
@patch("novel_system.llm.time.sleep")
def test_mimo_retries_on_500(mock_sleep, mock_post):
    fail = MagicMock()
    fail.status_code = 500
    success = MagicMock()
    success.status_code = 200
    success.json.return_value = {
        "content": [{"type": "text", "text": "ok after retry"}],
        "usage": {"input_tokens": 1, "output_tokens": 1, "cache_read_input_tokens": 0},
    }
    mock_post.side_effect = [fail, success]

    client = MimoClient(_mimo_config())
    with patch.object(type(client), "MAX_RETRIES", 1):
        with patch.object(type(client), "RETRY_DELAYS", [0]):
            res = client.chat([{"role": "user", "content": "hi"}])

    assert res.content == "ok after retry"
    assert mock_post.call_count == 2
