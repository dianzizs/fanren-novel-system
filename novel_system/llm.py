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
    """LLM chat response with optional token usage"""
    def __init__(self, content: str, usage: dict[str, int] | None = None) -> None:
        self.content = content
        self.usage = usage or {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}


class MiniMaxClient:
    # 重试配置
    MAX_RETRIES = 3
    RETRY_DELAYS = [1, 2, 4]  # 指数退避：1s, 2s, 4s

    def __init__(self, config: AppConfig) -> None:
        self.api_key = config.minimax_api_key
        self.base_url = config.minimax_base_url.rstrip("/")
        self.model = config.minimax_chat_model
        self.embedding_model = config.minimax_embedding_model

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

    def embed(
        self,
        texts: list[str],
        model: Optional[str] = None,
    ) -> list[list[float]]:
        """
        调用 MiniMax embedding API，带重试

        Args:
            texts: 文本列表（批量调用，每批最多 50 条）
            model: embedding 模型名，默认使用配置

        Returns:
            embedding 向量列表

        Raises:
            RuntimeError: 重试耗尽后抛出
        """
        if not self.enabled:
            raise RuntimeError("MiniMax API key not configured")

        model = model or self.embedding_model
        last_error: Optional[str] = None

        for attempt in range(self.MAX_RETRIES):
            try:
                response = requests.post(
                    f"{self.base_url}/embeddings",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    # MiniMax API 使用 "texts" 字段，需要 "type" 参数
                    # type: "query" 用于查询，"document" 用于文档
                    json={"model": model, "texts": texts, "type": "query"},
                    timeout=30,
                )
                response.raise_for_status()
                resp_json = response.json()
                # MiniMax API 返回 "vectors" 字段，不是 "data"
                vectors = resp_json.get("vectors")
                if vectors is None:
                    # 检查是否有错误
                    base_resp = resp_json.get("base_resp", {})
                    error_msg = base_resp.get("status_msg", "Unknown error")
                    raise RuntimeError(f"MiniMax embedding API error: {error_msg}")
                return vectors

            except requests.exceptions.Timeout:
                last_error = "API timeout"
                logger.warning(f"Embedding API timeout, attempt {attempt + 1}")

            except requests.exceptions.HTTPError as e:
                if e.response is not None and e.response.status_code in [429, 503]:
                    last_error = f"HTTP {e.response.status_code}"
                    logger.warning(f"Embedding API rate limited, attempt {attempt + 1}")
                else:
                    raise  # 认证等错误直接抛出

            except requests.exceptions.RequestException as e:
                last_error = str(e)
                logger.warning(f"Embedding API error: {e}, attempt {attempt + 1}")

            if attempt < self.MAX_RETRIES - 1:
                time.sleep(self.RETRY_DELAYS[attempt])

        raise RuntimeError(f"Embedding API failed after {self.MAX_RETRIES} retries: {last_error}")

