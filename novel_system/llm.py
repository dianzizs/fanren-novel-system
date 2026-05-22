"""LLM 客户端模块。

封装 MiniMax / Mimo API 调用，提供统一的对话接口。

关键导出：
- MiniMaxClient: 备用 LLM 路由器（MiniMax 优先，失败降级到 Mimo）
- MiniMaxDirectClient: 直接调用 MiniMax API 的底层客户端
- MimoClient: Anthropic-compatible Mimo API 客户端
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


class MiniMaxDirectClient:
    """MiniMax API 底层客户端。

    支持带重试的对话调用，自动处理 think 标签清理。
    对外请使用 MiniMaxClient（路由器），而非直接实例化此类。
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
    ) -> LLMResponse:
        """调用 MiniMax chat API。

        Args:
            messages: 对话消息列表
            temperature: 生成温度
            max_tokens: 最大生成 token 数

        Returns:
            LLMResponse（含 token 使用量）

        Raises:
            RuntimeError: API 未配置时抛出
        """
        if not self.enabled:
            raise RuntimeError("MINIMAX_API_KEY is not configured")

        for attempt in range(self.MAX_RETRIES + 1):
            try:
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
                
                # Check status codes that warrant a retry (rate limit or server issues)
                if response.status_code in (429, 500, 502, 503, 504):
                    if attempt < self.MAX_RETRIES:
                        delay = self.RETRY_DELAYS[attempt]
                        logger.warning(
                            f"LLM API returned status {response.status_code}. "
                            f"Retrying in {delay}s (attempt {attempt + 1}/{self.MAX_RETRIES})..."
                        )
                        time.sleep(delay)
                        continue
                
                response.raise_for_status()
                payload: dict[str, Any] = response.json()
                content = payload["choices"][0]["message"]["content"]
                usage = payload.get("usage")
                result = THINK_TAG_RE.sub("", content).strip()
                return LLMResponse(content=result, usage=usage)

            except (requests.exceptions.RequestException, KeyError, ValueError) as e:
                if attempt < self.MAX_RETRIES:
                    delay = self.RETRY_DELAYS[attempt]
                    logger.warning(
                        f"LLM API call failed with error: {e}. "
                        f"Retrying in {delay}s (attempt {attempt + 1}/{self.MAX_RETRIES})..."
                    )
                    time.sleep(delay)
                    continue
                else:
                    logger.error(f"LLM API call failed permanently after {self.MAX_RETRIES} retries.")
                    raise


class MimoClient:
    """Mimo API 客户端，遵循 Anthropic-compatible 协议。

    通过 Xiaomi Mimo 的 Anthropic-compatible 网关调用 LLM。
    支持带重试的对话调用，自动提取 system 消息，并规范化 token 用量字段。
    """

    MAX_RETRIES = 3
    RETRY_DELAYS = [1, 2, 4]  # 指数退避：1s, 2s, 4s

    def __init__(self, config: AppConfig) -> None:
        self.api_key = config.mimo_api_key
        self.base_url = config.mimo_base_url.rstrip("/")
        self.model = config.mimo_chat_model

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.2,
        max_tokens: int = 900,
    ) -> LLMResponse:
        """调用 Mimo Anthropic-compatible chat API。

        Args:
            messages: 对话消息列表（支持 system/user/assistant role）
            temperature: 生成温度
            max_tokens: 最大生成 token 数

        Returns:
            LLMResponse（含规范化后的 token 使用量）

        Raises:
            RuntimeError: API 未配置时抛出
        """
        if not self.enabled:
            raise RuntimeError(
                "MIMO_API_KEY / ANTHROPIC_AUTH_TOKEN is not configured"
            )

        # Anthropic 协议中 system 指令为顶层参数，需从 messages 中提取
        system_prompt: str | None = None
        formatted_messages: list[dict[str, str]] = []
        for msg in messages:
            if msg["role"] == "system":
                system_prompt = msg["content"]
            else:
                formatted_messages.append({"role": msg["role"], "content": msg["content"]})

        payload: dict = {
            "model": self.model,
            "messages": formatted_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if system_prompt:
            payload["system"] = system_prompt

        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }

        for attempt in range(self.MAX_RETRIES + 1):
            try:
                response = requests.post(
                    f"{self.base_url}/v1/messages",
                    headers=headers,
                    json=payload,
                    timeout=120,
                )

                if response.status_code in (429, 500, 502, 503, 504):
                    if attempt < self.MAX_RETRIES:
                        delay = self.RETRY_DELAYS[attempt]
                        logger.warning(
                            f"Mimo API returned {response.status_code}. "
                            f"Retrying in {delay}s (attempt {attempt + 1}/{self.MAX_RETRIES})..."
                        )
                        time.sleep(delay)
                        continue

                response.raise_for_status()
                res_data: dict = response.json()

                # 从 content blocks 中提取第一个 text block
                content = ""
                for block in res_data.get("content", []):
                    if block.get("type") == "text":
                        content = block.get("text", "")
                        break

                # 规范化 token 用量：Anthropic 格式 → 系统通用格式
                usage_data = res_data.get("usage", {})
                prompt_tokens = (
                    usage_data.get("input_tokens", 0)
                    + usage_data.get("cache_read_input_tokens", 0)
                )
                completion_tokens = usage_data.get("output_tokens", 0)
                usage = {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": prompt_tokens + completion_tokens,
                }

                result = THINK_TAG_RE.sub("", content).strip()
                return LLMResponse(content=result, usage=usage)

            except (requests.exceptions.RequestException, KeyError, ValueError) as e:
                if attempt < self.MAX_RETRIES:
                    delay = self.RETRY_DELAYS[attempt]
                    logger.warning(
                        f"Mimo API call failed: {e}. "
                        f"Retrying in {delay}s (attempt {attempt + 1}/{self.MAX_RETRIES})..."
                    )
                    time.sleep(delay)
                    continue
                logger.error(f"Mimo API call failed permanently after {self.MAX_RETRIES} retries.")
                raise


class MiniMaxClient:
    """备用 LLM 路由器。

    优先尝试 MiniMax；若 MiniMax 未配置或请求失败，自动降级到 Mimo。

    对外接口与历史 MiniMaxClient 完全兼容。
    """

    def __init__(self, config: AppConfig) -> None:
        self._minimax = MiniMaxDirectClient(config)
        self._mimo = MimoClient(config)

    @property
    def enabled(self) -> bool:
        return self._minimax.enabled or self._mimo.enabled

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.2,
        max_tokens: int = 900,
    ) -> LLMResponse:
        """路由对话请求到已配置的 LLM。

        顺序：先 MiniMax，失败则降级到 Mimo。
        若 MiniMax 未配置，直接路由到 Mimo。

        Raises:
            RuntimeError: 两个备用均未配置时抛出
        """
        if not self.enabled:
            raise RuntimeError(
                "Neither MINIMAX_API_KEY nor MIMO_API_KEY / ANTHROPIC_AUTH_TOKEN is configured."
            )

        if self._minimax.enabled:
            try:
                logger.info("Attempting MiniMax chat request...")
                return self._minimax.chat(
                    messages, temperature=temperature, max_tokens=max_tokens
                )
            except Exception as exc:  # noqa: BLE001
                if self._mimo.enabled:
                    logger.warning(
                        "MiniMax request failed (%s). Falling back to Mimo...", exc
                    )
                    return self._mimo.chat(
                        messages, temperature=temperature, max_tokens=max_tokens
                    )
                logger.error("MiniMax failed and Mimo is not configured.")
                raise

        logger.info("MiniMax not configured. Routing directly to Mimo...")
        return self._mimo.chat(
            messages, temperature=temperature, max_tokens=max_tokens
        )
