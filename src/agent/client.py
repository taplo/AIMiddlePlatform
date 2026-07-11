import logging
import os
from abc import ABC, abstractmethod
from typing import Any

import httpx

from src.core.config import settings

logger = logging.getLogger(__name__)


class LLMError(Exception):
    """Base LLM error."""

class LLMAPIError(LLMError):
    """API returned error status."""

class LLMTimeoutError(LLMError):
    """Request timed out."""

class LLMResponseError(LLMError):
    """Response parsing failed."""


class LLMClient(ABC):
    @abstractmethod
    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.1,
    ) -> dict[str, Any]:
        ...

    @abstractmethod
    async def chat_with_image(
        self,
        prompt: str,
        image_data: bytes,
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.1,
    ) -> dict[str, Any]:
        ...


def _build_multimodal_content(prompt: str, image_data: bytes) -> list[dict]:
    import base64
    encoded = base64.b64encode(image_data).decode("ascii")
    return [
        {"type": "text", "text": prompt},
        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{encoded}"}},
    ]


class QwenVLClient(LLMClient):
    def __init__(
        self,
        api_url: str | None = None,
        api_key: str | None = None,
        model_name: str | None = None,
        timeout: int = 30,
        max_retries: int = 2,
        http_client: httpx.AsyncClient | None = None,
    ):
        self.api_url = (api_url or settings.get("llm.api_url", "https://api.siliconflow.cn/v1")).rstrip("/")
        self.api_key = api_key or settings.get("llm.api_key", "") or os.getenv("LLM_API_KEY", "")
        self.model_name = model_name or settings.get("llm.model_name", "Qwen/Qwen2.5-VL-7B-Instruct")
        self.timeout = timeout
        self.max_retries = max_retries
        self._http = http_client or httpx.AsyncClient(timeout=httpx.Timeout(timeout))

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.1,
    ) -> dict[str, Any]:
        body = {
            "model": self.model_name,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": 1024,
        }
        return await self._call(body, tools)

    async def chat_with_image(
        self,
        prompt: str,
        image_data: bytes,
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.1,
    ) -> dict[str, Any]:
        content = _build_multimodal_content(prompt, image_data)
        body = {
            "model": self.model_name,
            "messages": [{"role": "user", "content": content}],
            "temperature": temperature,
            "max_tokens": 1024,
        }
        return await self._call(body, tools)

    async def _call(self, body: dict, tools: list[dict] | None) -> dict:
        if tools:
            body["tools"] = tools

        for attempt in range(self.max_retries + 1):
            try:
                response = await self._http.post(
                    f"{self.api_url}/chat/completions",
                    json=body,
                    headers={"Authorization": f"Bearer {self.api_key}"} if self.api_key else {},
                )
            except httpx.TimeoutException:
                if attempt < self.max_retries:
                    continue
                raise LLMTimeoutError(f"Request timed out after {self.timeout}s")

            if response.status_code == 400 and tools and body.get("tools"):
                logger.warning("API rejected tools (400), retrying without tools")
                body.pop("tools", None)
                body["response_format"] = {"type": "json_object"}
                continue

            if response.status_code >= 400:
                raise LLMAPIError(f"API error {response.status_code}: {response.text[:200]}")

            try:
                data = response.json()
            except Exception as e:
                raise LLMResponseError(f"Non-JSON response: {e}")

            message = data["choices"][0]["message"]
            return {
                "role": message.get("role", "assistant"),
                "content": message.get("content", ""),
                "tool_calls": message.get("tool_calls"),
            }

        raise LLMAPIError("Max retries exceeded")


class DeepSeekVLClient(QwenVLClient):
    def __init__(self, **kwargs):
        kwargs.setdefault("api_url", "https://api.deepseek.com/v1")
        kwargs.setdefault("model_name", "deepseek-vl-7b-chat")
        super().__init__(**kwargs)
