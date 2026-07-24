import base64
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

    @abstractmethod
    async def ping(self) -> bool:
        ...

    @abstractmethod
    async def aclose(self) -> None:
        ...


def _build_multimodal_content(prompt: str, image_data: bytes) -> list[dict]:
    encoded = base64.b64encode(image_data).decode("ascii")
    return [
        {"type": "text", "text": prompt},
        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{encoded}"}},
    ]


class OpenAIClient(LLMClient):
    """OpenAI-compatible API client (works with SiliconFlow, DeepSeek, LM Studio, etc.)."""

    PROVIDER = "openai"

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
        self._owned_http = http_client is None

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

    async def verify(
        self,
        image_data: bytes,
        label: str,
        confidence: float,
    ) -> dict:
        from src.agent.agent import _extract_json
        prompt = (
            f"这张图片被检测为「{label}」，置信度 {confidence:.1%}。"
            f"请确认这个目标是否正确。如果正确，返回 verified=true；"
            f"如果错误，返回 verified=false 并给出正确的 label。"
            f"用 JSON 格式回答：{{verified: bool, corrected_label: str, reason: str}}"
        )
        response = await self.chat_with_image(prompt, image_data)
        content = response.get("content", "")
        parsed = _extract_json(content) or {}
        return {
            "verified": parsed.get("verified", False),
            "corrected_label": parsed.get("corrected_label", label),
            "reason": parsed.get("reason", ""),
        }

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

    async def ping(self) -> bool:
        try:
            resp = await self._http.get(f"{self.api_url}/models", timeout=5.0)
            return resp.status_code < 500
        except Exception:
            return False

    async def aclose(self) -> None:
        await self._http.aclose()


class OllamaClient(LLMClient):
    """Ollama native API client."""

    PROVIDER = "ollama"

    def __init__(
        self,
        api_url: str | None = None,
        api_key: str | None = None,
        model_name: str | None = None,
        timeout: int = 30,
        max_retries: int = 2,
        http_client: httpx.AsyncClient | None = None,
    ):
        self.api_url = (api_url or "http://localhost:11434").rstrip("/")
        self.api_key = api_key or ""
        self.model_name = model_name or "llama3.2-vision"
        self.timeout = timeout
        self.max_retries = max_retries
        self._http = http_client or httpx.AsyncClient(timeout=httpx.Timeout(timeout))
        self._owned_http = http_client is None

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.1,
    ) -> dict[str, Any]:
        body = {
            "model": self.model_name,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature},
        }
        return await self._call(body, tools)

    async def chat_with_image(
        self,
        prompt: str,
        image_data: bytes,
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.1,
    ) -> dict[str, Any]:
        encoded = base64.b64encode(image_data).decode("ascii")
        body = {
            "model": self.model_name,
            "messages": [{"role": "user", "content": prompt, "images": [encoded]}],
            "stream": False,
            "options": {"temperature": temperature},
        }
        return await self._call(body, tools)

    async def verify(
        self,
        image_data: bytes,
        label: str,
        confidence: float,
    ) -> dict:
        from src.agent.agent import _extract_json
        prompt = (
            f"这张图片被检测为「{label}」，置信度 {confidence:.1%}。"
            f"请确认这个目标是否正确。如果正确，返回 verified=true；"
            f"如果错误，返回 verified=false 并给出正确的 label。"
            f"用 JSON 格式回答：{{verified: bool, corrected_label: str, reason: str}}"
        )
        response = await self.chat_with_image(prompt, image_data)
        content = response.get("content", "")
        parsed = _extract_json(content) or {}
        return {
            "verified": parsed.get("verified", False),
            "corrected_label": parsed.get("corrected_label", label),
            "reason": parsed.get("reason", ""),
        }

    async def _call(self, body: dict, tools: list[dict] | None) -> dict:
        if tools:
            body["tools"] = tools

        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        for attempt in range(self.max_retries + 1):
            try:
                response = await self._http.post(
                    f"{self.api_url}/api/chat",
                    json=body,
                    headers=headers,
                )
            except httpx.TimeoutException:
                if attempt < self.max_retries:
                    continue
                raise LLMTimeoutError(f"Request timed out after {self.timeout}s")

            if response.status_code >= 400:
                raise LLMAPIError(f"Ollama API error {response.status_code}: {response.text[:200]}")

            try:
                data = response.json()
            except Exception as e:
                raise LLMResponseError(f"Non-JSON response: {e}")

            message = data.get("message", {})
            return {
                "role": message.get("role", "assistant"),
                "content": message.get("content", ""),
                "tool_calls": None,
            }

        raise LLMAPIError("Max retries exceeded")

    async def ping(self) -> bool:
        try:
            resp = await self._http.get(f"{self.api_url}/api/tags", timeout=5.0)
            return resp.status_code < 500
        except Exception:
            return False

    async def aclose(self) -> None:
        await self._http.aclose()


_PROVIDER_MAP: dict[str, type[LLMClient]] = {
    "openai": OpenAIClient,
    "ollama": OllamaClient,
    "lm_studio": OpenAIClient,
}

_PROVIDER_DEFAULTS: dict[str, dict[str, str]] = {
    "openai": {
        "api_url": "https://api.siliconflow.cn/v1",
        "model_name": "Qwen/Qwen2.5-VL-7B-Instruct",
    },
    "ollama": {
        "api_url": "http://localhost:11434",
        "model_name": "llama3.2-vision",
    },
    "lm_studio": {
        "api_url": "http://localhost:1234/v1",
        "model_name": "",
    },
}


def create_llm_client(
    provider: str = "openai",
    api_url: str | None = None,
    api_key: str | None = None,
    model_name: str | None = None,
    **kwargs,
) -> LLMClient:
    provider = provider.lower().replace("-", "_")
    client_cls = _PROVIDER_MAP.get(provider, OpenAIClient)
    defaults = _PROVIDER_DEFAULTS.get(provider, {})
    return client_cls(
        api_url=api_url or defaults.get("api_url"),
        api_key=api_key,
        model_name=model_name or defaults.get("model_name"),
        **kwargs,
    )


def get_providers() -> list[dict[str, str]]:
    return [
        {"id": "openai", "name": "OpenAI 兼容 (SiliconFlow / DeepSeek等)", "default_url": "https://api.siliconflow.cn/v1"},
        {"id": "ollama", "name": "Ollama (本地)", "default_url": "http://localhost:11434"},
        {"id": "lm_studio", "name": "LM Studio (本地)", "default_url": "http://localhost:1234/v1"},
    ]


# Backward-compat aliases
QwenVLClient = OpenAIClient


class DeepSeekVLClient(OpenAIClient):
    def __init__(self, **kwargs):
        kwargs.setdefault("api_url", "https://api.deepseek.com/v1")
        kwargs.setdefault("model_name", "deepseek-vl-7b-chat")
        super().__init__(**kwargs)
