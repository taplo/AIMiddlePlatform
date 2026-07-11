import json
import logging
import time
import re
from typing import Any

from src.agent.client import LLMClient
from src.agent.tools import ToolRegistry

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "你是一个计算机视觉分析助手。分析图像内容并输出结构化 JSON。\n\n"
    "任务：\n"
    "1. 描述场景类型（室内/室外/交通/安防/其他）\n"
    "2. 列出检测到的目标及其属性\n"
    "3. 识别异常情况（如有）\n\n"
    "输出格式：\n"
    "{\n"
    '    "scene_type": "string",\n'
    '    "objects": [{"label": "string", "count": int, "details": "string"}],\n'
    '    "anomalies": [{"type": "string", "description": "string", "confidence": float}],\n'
    '    "summary": "string"\n'
    "}\n\n"
    "如果图像无法分析，返回 {\"error\": \"无法分析图像\", \"reason\": \"...\"}。"
)


def _extract_json(text: str) -> dict | None:
    if not text:
        return None
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            pass
    return None


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

        if image_data:
            response = await self.llm.chat_with_image(
                prompt=json.dumps(scene_context, ensure_ascii=False),
                image_data=image_data,
                tools=tool_specs if tool_specs else None,
            )
        else:
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

        analysis = _extract_json(response.get("content", "")) or response.get("content", "")

        elapsed = (time.monotonic() - start) * 1000

        return {
            "path": "agent",
            "analysis": analysis,
            "tool_results": tool_results,
            "latency_ms": elapsed,
        }

    async def analyze_with_image(
        self,
        scene_context: dict[str, Any],
        image_data: bytes,
    ) -> dict[str, Any]:
        return await self.analyze(scene_context, image_data=image_data)
