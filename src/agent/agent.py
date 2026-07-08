import json
import logging
import time
from typing import Any

from src.agent.client import LLMClient
from src.agent.tools import ToolRegistry

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are a CV analysis agent. Analyze the scene and execute appropriate tools "
    "to extract structured information. Respond with a JSON summary of findings."
)


class CVAgent:
    def __init__(self, llm_client: LLMClient, tool_registry: ToolRegistry):
        self.llm = llm_client
        self.tools = tool_registry

    async def analyze(
        self,
        scene_context: dict[str, Any],
        image_data: bytes | None = None,
    ) -> dict[str, Any]:
        start = time.monotonic()

        tool_specs = self.tools.get_openai_specs()
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(scene_context, ensure_ascii=False)},
        ]

        response = await self.llm.chat(
            messages=messages,
            tools=tool_specs if tool_specs else None,
        )

        tool_results = {}
        tool_calls = response.get("tool_calls")
        if tool_calls:
            for tc in tool_calls:
                name = tc["function"]["name"]
                args = json.loads(tc["function"]["arguments"])
                result = await self.tools.execute_tool(name, args)
                tool_results[name] = result

        elapsed = (time.monotonic() - start) * 1000

        return {
            "path": "agent",
            "analysis": response.get("content", ""),
            "tool_results": tool_results,
            "latency_ms": elapsed,
        }

    async def analyze_with_image(
        self,
        scene_context: dict[str, Any],
        image_data: bytes,
    ) -> dict[str, Any]:
        start = time.monotonic()

        prompt = json.dumps(scene_context, ensure_ascii=False)
        tool_specs = self.tools.get_openai_specs()

        response = await self.llm.chat_with_image(
            prompt=prompt,
            image_data=image_data,
            tools=tool_specs if tool_specs else None,
        )

        tool_results = {}
        tool_calls = response.get("tool_calls")
        if tool_calls:
            for tc in tool_calls:
                name = tc["function"]["name"]
                args = json.loads(tc["function"]["arguments"])
                result = await self.tools.execute_tool(name, args)
                tool_results[name] = result

        elapsed = (time.monotonic() - start) * 1000

        return {
            "path": "agent",
            "analysis": response.get("content", ""),
            "tool_results": tool_results,
            "latency_ms": elapsed,
        }
