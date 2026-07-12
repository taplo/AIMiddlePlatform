# P2: Agent 路径真实化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace QwenVLClient/DeepSeekVLClient stubs with real HTTP calls (OpenAI-compatible), improve CVAgent prompts, and integrate Agent path into Worker.

**Architecture:** httpx.AsyncClient-based client with MockTransport for testing. CVAgent uses CV-domain system prompt with JSON structured output and tool_calls fallback. Worker creates AgentOrchestrator to handle FastPath-missed frames.

**Tech Stack:** Python 3.12+, httpx 0.28+, FastAPI, pytest-asyncio

## Global Constraints

- Existing `LLMClient` ABC interface (`chat()` and `chat_with_image()`) must be preserved
- `httpx.AsyncClient` injected via constructor for testability (no monkey-patching)
- All 132+ existing tests must continue to pass
- OpenAI-compatible chat completions endpoint format (`/v1/chat/completions`)
- MockTransport from `httpx` — no additional test dependencies
- Settings from `src.core.config.settings.get("llm.*")` + env var `LLM_API_KEY`

---

### Task 1: LLM 配置项

**Files:**
- Modify: `config/default.yaml`

**Interfaces:**
- Produces: `settings.get("llm.api_url")`, `settings.get("llm.api_key")`, `settings.get("llm.model_name")`, `settings.get("llm.timeout")`, `settings.get("llm.max_retries")`

- [ ] **Step 1: 添加 llm 配置到 default.yaml**

```yaml
# config/default.yaml 末尾添加
llm:
  api_url: https://api.siliconflow.cn/v1
  api_key: ""
  model_name: Qwen/Qwen2.5-VL-7B-Instruct
  timeout: 30
  max_retries: 2
```

- [ ] **Step 2: 提交**

```bash
git add config/default.yaml
git commit -m "feat: add LLM configuration section to default.yaml"
```

---

### Task 2: QwenVLClient 真实 HTTP 实现

**Files:**
- Modify: `src/agent/client.py`（完整重写 QwenVLClient）
- Modify: `tests/test_agent.py`（更新所有 client 测试）

**Interfaces:**
- Consumes: `settings.get("llm.*")`, `LLMClient` ABC (unchanged)
- Consumes: `httpx.AsyncClient` (injected via constructor)
- Produces: `QwenVLClient(api_url, api_key, model_name, timeout, max_retries, http_client)`
- Produces: `client.chat(messages, tools, temperature) -> dict` — returns `{"role": "assistant", "content": str, "tool_calls": list | None}`
- Produces: `client.chat_with_image(prompt, image_data, tools, temperature) -> dict` — same return shape
- Produces: Error classes: `LLMError`, `LLMAPIError`, `LLMTimeoutError`, `LLMResponseError`

- [ ] **Step 1: 写失败测试（新 client 接口 + 错误类）**

```python
# tests/test_agent.py — 替换全部内容
import pytest
import httpx
import json

from src.agent.client import (
    QwenVLClient, DeepSeekVLClient,
    LLMError, LLMAPIError, LLMTimeoutError, LLMResponseError,
)


def _mock_transport(response_json: dict, status_code: int = 200):
    return httpx.MockTransport(lambda req: httpx.Response(status_code, json=response_json))


@pytest.mark.asyncio
async def test_qwen_chat_returns_content():
    transport = _mock_transport({
        "choices": [{"message": {"content": "Hello!", "role": "assistant"}}]
    })
    client = QwenVLClient(http_client=httpx.AsyncClient(transport=transport))
    response = await client.chat([{"role": "user", "content": "hi"}])
    assert response["content"] == "Hello!"
    assert response["tool_calls"] is None


@pytest.mark.asyncio
async def test_qwen_chat_with_tools():
    transport = _mock_transport({
        "choices": [{
            "message": {
                "content": None,
                "role": "assistant",
                "tool_calls": [
                    {"id": "call_1", "type": "function",
                     "function": {"name": "detect_objects", "arguments": '{"image": "base64..."}'}}
                ]
            }
        }]
    })
    client = QwenVLClient(http_client=httpx.AsyncClient(transport=transport))
    response = await client.chat(
        [{"role": "user", "content": "detect objects"}],
        tools=[{"type": "function", "function": {"name": "detect_objects"}}],
    )
    assert response["tool_calls"] is not None
    assert response["tool_calls"][0]["function"]["name"] == "detect_objects"


@pytest.mark.asyncio
async def test_qwen_chat_with_image():
    transport = _mock_transport({
        "choices": [{"message": {"content": "A traffic scene", "role": "assistant"}}]
    })
    client = QwenVLClient(http_client=httpx.AsyncClient(transport=transport))
    response = await client.chat_with_image("What is this?", b"fake_image_data")
    assert response["content"] == "A traffic scene"


@pytest.mark.asyncio
async def test_qwen_fallback_json_on_tool_call_failure():
    """When API returns 400 for tools, retry without tools + response_format=json_object"""
    called_first = False

    def handler(req):
        nonlocal called_first
        if not called_first:
            called_first = True
            return httpx.Response(400, json={"error": "tools not supported"})
        return httpx.Response(200, json={
            "choices": [{"message": {"content": '{"scene_type": "traffic"}', "role": "assistant"}}]
        })

    client = QwenVLClient(http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    response = await client.chat(
        [{"role": "user", "content": "analyze"}],
        tools=[{"type": "function", "function": {"name": "detect_objects"}}],
    )
    assert response["content"] is not None


@pytest.mark.asyncio
async def test_qwen_raises_on_api_error():
    transport = _mock_transport({"error": "unauthorized"}, status_code=401)
    client = QwenVLClient(http_client=httpx.AsyncClient(transport=transport))
    with pytest.raises(LLMAPIError, match="401"):
        await client.chat([{"role": "user", "content": "hi"}])


@pytest.mark.asyncio
async def test_qwen_deepseek_defaults():
    client = DeepSeekVLClient(http_client=httpx.AsyncClient(transport=_mock_transport({
        "choices": [{"message": {"content": "ok", "role": "assistant"}}]
    })))
    response = await client.chat([{"role": "user", "content": "hi"}])
    assert response["content"] == "ok"
```

- [ ] **Step 2: 运行测试确认失败**

```bash
$env:PYTHONPATH = "D:\projects\AIMiddlePlatform"; uv run python -m pytest tests/test_agent.py -v --tb=short
Expected: 6 failed — import errors (LLMError, etc. not defined)
```

- [ ] **Step 3: 实现 client.py（完整重写）**

```python
# src/agent/client.py
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
```

- [ ] **Step 4: 运行测试确认通过**

```bash
$env:PYTHONPATH = "D:\projects\AIMiddlePlatform"; uv run python -m pytest tests/test_agent.py -v --tb=short
Expected: 6 passed
```

- [ ] **Step 5: 提交**

```bash
git add src/agent/client.py tests/test_agent.py
git commit -m "feat: real HTTP implementation for QwenVLClient and DeepSeekVLClient"
```

---

### Task 3: CVAgent 提示词 + JSON 解析

**Files:**
- Modify: `src/agent/agent.py`
- Modify: `tests/test_agent.py`（追加测试）

**Interfaces:**
- Consumes: `LLMClient.chat()` / `chat_with_image()` from Task 2
- Consumes: `ToolRegistry` from existing `src/agent/tools.py`
- Produces: `CVAgent.analyze(scene_context, image_data) -> dict` with real LLM call + tool execution or JSON parsing
- Produces: `_extract_json(text) -> dict` utility

- [ ] **Step 1: 写测试**

```python
# tests/test_agent.py — 追加到文件末尾

@pytest.mark.asyncio
async def test_agent_analyze_with_json_response():
    """Agent parses JSON from content when no tool_calls returned."""
    transport = httpx.MockTransport(lambda req: httpx.Response(200, json={
        "choices": [{"message": {
            "content": '{"scene_type": "traffic", "objects": [{"label": "car", "count": 3}], "anomalies": [], "summary": "busy intersection"}',
            "role": "assistant",
        }}]
    }))
    from src.agent.agent import CVAgent
    from src.agent.tools import ToolRegistry
    from src.models.inference import InferenceOrchestrator
    from src.models.registry import ModelRegistry
    client = QwenVLClient(http_client=httpx.AsyncClient(transport=transport))
    agent = CVAgent(client, ToolRegistry(InferenceOrchestrator(ModelRegistry())))
    result = await agent.analyze({"scene": "intersection"})
    assert result["path"] == "agent"
    assert "scene_type" in result["analysis"]
    assert result["analysis"]["scene_type"] == "traffic"


@pytest.mark.asyncio
async def test_agent_analyze_with_image():
    transport = httpx.MockTransport(lambda req: httpx.Response(200, json={
        "choices": [{"message": {
            "content": '{"scene_type": "office", "objects": [], "anomalies": [], "summary": "empty room"}',
            "role": "assistant",
        }}]
    }))
    from src.agent.agent import CVAgent
    from src.agent.tools import ToolRegistry
    from src.models.inference import InferenceOrchestrator
    from src.models.registry import ModelRegistry
    client = QwenVLClient(http_client=httpx.AsyncClient(transport=transport))
    agent = CVAgent(client, ToolRegistry(InferenceOrchestrator(ModelRegistry())))
    result = await agent.analyze({"scene": "office"}, image_data=b"fake_image")
    assert result["path"] == "agent"
    assert result["analysis"]["scene_type"] == "office"


@pytest.mark.asyncio
async def test_agent_executes_tool_calls():
    """Agent executes tools returned by LLM and includes results."""
    transport = httpx.MockTransport(lambda req: httpx.Response(200, json={
        "choices": [{"message": {
            "content": None,
            "role": "assistant",
            "tool_calls": [
                {"id": "call_1", "type": "function",
                 "function": {"name": "detect_objects", "arguments": '{"image": "base64"}'}}
            ],
        }}]
    }))
    from src.agent.agent import CVAgent
    from src.agent.tools import ToolRegistry, build_cv_tools
    from src.models.inference import InferenceOrchestrator
    from src.models.registry import ModelRegistry

    class StubAdapter:
        async def predict(self, spec, inp):
            return {"output": {"objects": [{"label": "person"}]}}
    registry = ModelRegistry()
    from src.models.registry import ModelSpec
    registry.register(ModelSpec(model_id="object_detection", name="OD", version="1.0.0"))
    orchestrator = InferenceOrchestrator(registry)
    orchestrator.register_adapter("onnx", StubAdapter())
    tool_registry = ToolRegistry(orchestrator)
    build_cv_tools(tool_registry)

    client = QwenVLClient(http_client=httpx.AsyncClient(transport=transport))
    agent = CVAgent(client, tool_registry)
    result = await agent.analyze({"scene": "intersection"})
    assert result["path"] == "agent"
    assert "detect_objects" in result["tool_results"]


@pytest.mark.asyncio
async def test_extract_json_from_code_block():
    from src.agent.agent import _extract_json
    text = "Some text\n```json\n{\"key\": \"value\"}\n```\nmore text"
    assert _extract_json(text) == {"key": "value"}


@pytest.mark.asyncio
async def test_extract_json_direct():
    from src.agent.agent import _extract_json
    text = '{"key": "value"}'
    assert _extract_json(text) == {"key": "value"}
```

- [ ] **Step 2: 运行测试确认失败**

```bash
$env:PYTHONPATH = "D:\projects\AIMiddlePlatform"; uv run python -m pytest tests/test_agent.py -v --tb=short
Expected: 6 existing pass + 5 new fail (4 agent + 1 import)
```

- [ ] **Step 3: 实现 agent.py**

```python
# src/agent/agent.py
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
```

- [ ] **Step 4: 运行测试确认通过**

```bash
$env:PYTHONPATH = "D:\projects\AIMiddlePlatform"; uv run python -m pytest tests/test_agent.py -v --tb=short
Expected: 11 passed
```

- [ ] **Step 5: 提交**

```bash
git add src/agent/agent.py tests/test_agent.py
git commit -m "feat: CV-domain prompts and JSON parsing for CVAgent"
```

---

### Task 4: Worker Agent 路径集成

**Files:**
- Modify: `src/worker.py`
- Modify: `tests/test_worker.py`

**Interfaces:**
- Consumes: `AgentOrchestrator` from `src/agent/orchestrator.py`
- Consumes: `CVAgent`, `QwenVLClient`, `ToolRegistry`, `build_cv_tools` from agent module
- Produces: `Worker.process_one()` falls through to Agent path when FastPath returns None

- [ ] **Step 1: 写测试**

```python
# tests/test_worker.py — 追加到文件末尾
import pytest
import httpx
from src.agent.client import QwenVLClient
from sqlalchemy.ext.asyncio import AsyncSession
from src.worker import Worker
from src.core.database import init_db, Task


@pytest.mark.asyncio
async def test_worker_falls_through_to_agent():
    """When FastPath returns None, Worker should fall through to Agent path."""
    db = await init_db("sqlite+aiosqlite:///:memory:")

    # Mock the LLM response
    transport = httpx.MockTransport(lambda req: httpx.Response(200, json={
        "choices": [{"message": {
            "content": '{"scene_type": "unknown", "objects": [], "anomalies": [], "summary": "no fast path match"}',
            "role": "assistant",
        }}]
    }))
    from src.worker import Worker
    worker = Worker(db)
    # Override orchestrator agent with mocked LLM
    from src.agent.client import QwenVLClient
    worker.orchestrator.agent.llm = QwenVLClient(http_client=httpx.AsyncClient(transport=transport))

    msg = {
        "task_id": "agent-test-001",
        "camera_id": "cam-unknown",
        "frame": "",
        "scene_type": "unknown",
    }
    result = await worker.process_one(msg)
    # unknown scene → FastPath returns None → Agent path
    assert result is not None
    assert result["path"] == "agent"

    async with AsyncSession(db) as session:
        task = await session.get(Task, "agent-test-001")
        assert task is not None
        assert task.path_taken == "agent"
```

- [ ] **Step 2: 运行测试确认失败**

```bash
$env:PYTHONPATH = "D:\projects\AIMiddlePlatform"; uv run python -m pytest tests/test_worker.py -v --tb=short
Expected: 1 existing pass + 1 new fail
```

- [ ] **Step 3: 修改 worker.py**

Add AgentOrchestrator initialization in Worker.__init__ and update process_one for Agent path.

Current `process_one` does:
```python
result = await self.fast_path.process(message)
if result is None:
    result = {"path": "agent", "analysis": "stub", "latency_ms": latency}
```

Replace with actual Agent call:
```python
result = await self.fast_path.process(message)
if result is None:
    frame_raw = message.get("frame", "")
    if frame_raw:
        image = _decode_frame(frame_raw)
    else:
        image = None
    result = await self.orchestrator.agent.analyze(message, image_data=image)
    result.setdefault("latency_ms", latency)
```

And in `__init__`, add AgentOrchestrator initialization:

After fast_path init:
```python
from src.agent.tools import ToolRegistry, build_cv_tools
from src.agent.client import QwenVLClient
from src.agent.agent import CVAgent
from src.agent.orchestrator import AgentOrchestrator

tool_registry = ToolRegistry(_inference)
build_cv_tools(tool_registry)
agent = CVAgent(QwenVLClient(), tool_registry)
self.orchestrator = AgentOrchestrator(self.fast_path, agent, _inference)
```

Full modified Worker class (complete file):

```python
# src/worker.py
import json
import logging
import asyncio
from typing import Any

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.core.database import Task
from src.queue.redis_streams import RedisStreamQueue
from src.routing.fast_path import FastPathHandler
from src.models.inference import InferenceOrchestrator
from src.models.registry import ModelRegistry
from src.models.presets import register_default_models
from src.models.adapters.yolov8_adapter import YOLOv8Adapter
from src.pipeline.registry import PipelineRegistry
from src.pipeline.executor import DAGExecutor
from src.pipeline.dag import DAGDefinition, DAGNode, NodeType
from src.routing.scene_router import SceneRouter
from src.agent.orchestrator import AgentOrchestrator
from src.agent.tools import ToolRegistry, build_cv_tools
from src.agent.client import QwenVLClient
from src.agent.agent import CVAgent

logger = logging.getLogger(__name__)


def _init_inference() -> InferenceOrchestrator:
    registry = ModelRegistry()
    register_default_models(registry)
    inference = InferenceOrchestrator(registry)
    inference.register_adapter("onnx", YOLOv8Adapter(model_dir="models"))
    return inference


def _init_fast_path() -> tuple[SceneRouter, PipelineRegistry, DAGExecutor, FastPathHandler]:
    router = SceneRouter()
    registry = PipelineRegistry()
    executor = DAGExecutor()
    executor.register_handler(NodeType.MODEL_INFERENCE, _inference_handler)
    _register_default_pipelines(registry)
    handler = FastPathHandler(router, registry, executor)
    return router, registry, executor, handler


def _register_default_pipelines(registry: PipelineRegistry) -> None:
    pipelines = {
        "plate_recognition": [DAGNode("detect_plate", NodeType.MODEL_INFERENCE, config={"model": "license_plate"})],
        "object_detection": [DAGNode("detect_objects", NodeType.MODEL_INFERENCE, config={"model": "object_detection"})],
        "face_recognition": [DAGNode("detect_faces", NodeType.MODEL_INFERENCE, config={"model": "face_recognition"})],
        "vehicle_detection": [DAGNode("detect_vehicles", NodeType.MODEL_INFERENCE, config={"model": "vehicle_detection"})],
        "ocr": [DAGNode("ocr_text", NodeType.MODEL_INFERENCE, config={"model": "ocr"})],
    }
    for name, nodes in pipelines.items():
        dag = DAGDefinition(name=name)
        for n in nodes:
            dag.add_node(n)
        registry.register(name, dag)


def _decode_frame(frame: str):
    import base64
    import cv2
    import numpy as np
    try:
        raw = base64.b64decode(frame)
        arr = np.frombuffer(raw, dtype=np.uint8)
        return cv2.imdecode(arr, cv2.IMREAD_COLOR)
    except Exception:
        return None


def _inference_handler(context: dict, input_data: dict, node_config: dict) -> dict:
    model_id = node_config.get("model", "")
    if not model_id:
        return {"error": "no model_id in node_config"}
    raw = context.get("frame")
    if raw is None:
        return {"error": "no frame in context"}
    image = _decode_frame(raw)
    if image is None:
        return {"error": "failed to decode frame"}
    import asyncio
    result = asyncio.run(_inference.infer(model_id, {"image": image}))
    return result


_inference: InferenceOrchestrator | None = None


class Worker:
    def __init__(self, db_engine: AsyncEngine):
        self.db = db_engine
        global _inference
        _inference = _init_inference()
        _, _, _, self.fast_path = _init_fast_path()
        tool_registry = ToolRegistry(_inference)
        build_cv_tools(tool_registry)
        agent = CVAgent(QwenVLClient(), tool_registry)
        self.orchestrator = AgentOrchestrator(self.fast_path, agent, _inference)

    async def process_one(self, message: dict) -> dict:
        task_id = message.get("task_id", "unknown")
        camera_id = message.get("camera_id", "unknown")
        start = asyncio.get_event_loop().time()

        result = await self.fast_path.process(message)

        latency = (asyncio.get_event_loop().time() - start) * 1000
        if result is None:
            frame_raw = message.get("frame", "")
            image = _decode_frame(frame_raw) if frame_raw else None
            result = await self.orchestrator.agent.analyze(message, image_data=image)
            result.setdefault("latency_ms", latency)

        await self._save_result(task_id, camera_id, result)
        return result

    async def _save_result(self, task_id: str, camera_id: str, result: dict):
        import json
        async with AsyncSession(self.db) as session:
            task = Task(
                id=task_id,
                camera_id=camera_id,
                path_taken=result.get("path", "unknown"),
                status="completed",
                result_json=json.dumps(result, default=str),
                latency_ms=int(result.get("latency_ms", 0)),
            )
            session.add(task)
            await session.commit()


async def run_worker(db_url: str = "sqlite+aiosqlite:///data/aimp.db"):
    from src.core.database import init_db
    db = await init_db(db_url)
    worker = Worker(db)
    queue = RedisStreamQueue()

    logger.info("Worker started, consuming from aimp:tasks")
    async for raw in queue.consume("aimp:tasks"):
        try:
            msg = json.loads(raw)
            await worker.process_one(msg)
        except Exception as e:
            logger.error("Failed to process message: %s", e)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_worker())
```

- [ ] **Step 4: 运行测试确认通过**

```bash
$env:PYTHONPATH = "D:\projects\AIMiddlePlatform"; uv run python -m pytest tests/test_worker.py -v --tb=short
Expected: 2 passed
```

- [ ] **Step 5: 提交**

```bash
git add src/worker.py tests/test_worker.py
git commit -m "feat: integrate Agent path into Worker with real CVAgent"
```

---

### Task 5: 回归测试 + 提交

**Files:**
- No code changes — only verification

- [ ] **Step 1: 运行全部测试**

```bash
$env:PYTHONPATH = "D:\projects\AIMiddlePlatform"; uv run python -m pytest tests/ -q --tb=short 2>&1
Expected: All passed (previous 132 + new agent/worker tests)
```

- [ ] **Step 2: 如果全部通过，提交**

```bash
git add -A
git commit -m "chore: full regression pass for P2 agent path realization"
```
