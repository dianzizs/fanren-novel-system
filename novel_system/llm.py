"""LLM 客户端模块。

封装 MiniMax API 调用，提供统一的对话接口。

关键导出：
- MiniMaxClient: MiniMax API 客户端
- LLMResponse: 包含内容和 token 使用量的响应对象
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any, Optional

import requests

from .config import AppConfig

logger = logging.getLogger(__name__)


THINK_TAG_RE = re.compile(r"<think>.*?</think>\s*", re.DOTALL | re.IGNORECASE)


class LLMResponse:
    """LLM 响应，包含生成内容和 token 使用量。"""

    def __init__(self, content: str, usage: dict[str, int] | None = None) -> None:
        self.content = content
        self.usage = usage or {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}


class MiniMaxClient:
    """MiniMax API 客户端。

    支持带重试的对话调用，自动处理 think 标签清理。
    """

    # 重试配置
    MAX_RETRIES = 3
    RETRY_DELAYS = [1, 2, 4]  # 指数退避：1s, 2s, 4s

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
    ) -> str | LLMResponse:
        """调用 MiniMax chat API。

        Args:
            messages: 对话消息列表
            temperature: 生成温度
            max_tokens: 最大生成 token 数

        Returns:
            LLMResponse（含 token 使用量）或纯字符串

        Raises:
            RuntimeError: API 未配置时抛出
        """
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
        usage = payload.get("usage")
        result = THINK_TAG_RE.sub("", content).strip()
        if usage:
            return LLMResponse(content=result, usage=usage)
        return result

