import logging
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)


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


class QwenVLClient(LLMClient):
    def __init__(self, api_url: str = "http://localhost:8000/v1", api_key: str = ""):
        self.api_url = api_url
        self.api_key = api_key

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.1,
    ) -> dict[str, Any]:
        logger.info("Qwen-VL chat stub: %d messages", len(messages))
        return {"role": "assistant", "content": "Scene analysis stub result", "tool_calls": None}

    async def chat_with_image(
        self,
        prompt: str,
        image_data: bytes,
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.1,
    ) -> dict[str, Any]:
        logger.info("Qwen-VL image chat stub: %s", prompt[:50])
        return {"role": "assistant", "content": "Image analysis stub result", "tool_calls": None}


class DeepSeekVLClient(LLMClient):
    def __init__(self, api_url: str = "http://localhost:8000/v1", api_key: str = ""):
        self.api_url = api_url
        self.api_key = api_key

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.1,
    ) -> dict[str, Any]:
        logger.info("DeepSeek-VL chat stub: %d messages", len(messages))
        return {"role": "assistant", "content": "DeepSeek analysis stub result", "tool_calls": None}

    async def chat_with_image(
        self,
        prompt: str,
        image_data: bytes,
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.1,
    ) -> dict[str, Any]:
        logger.info("DeepSeek-VL image chat stub: %s", prompt[:50])
        return {"role": "assistant", "content": "DeepSeek image analysis stub result", "tool_calls": None}
