from __future__ import annotations

import re
from typing import Any

import requests

from .config import AppConfig


THINK_TAG_RE = re.compile(r"<think>.*?</think>\s*", re.DOTALL | re.IGNORECASE)


class MiniMaxClient:
    def __init__(self, config: AppConfig) -> None:
        self.api_key = config.minimax_api_key
        self.base_url = config.minimax_base_url.rstrip("/")
        self.model = config.minimax_chat_model

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.2,
        max_tokens: int = 900,
    ) -> str:
        if not self.enabled:
            raise RuntimeError("MINIMAX_API_KEY is not configured")
        response = requests.post(
            f"{self.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
            timeout=120,
        )
        response.raise_for_status()
        payload: dict[str, Any] = response.json()
        content = payload["choices"][0]["message"]["content"]
        return THINK_TAG_RE.sub("", content).strip()

