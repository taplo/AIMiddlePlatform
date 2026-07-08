import pytest

from src.agent.client import QwenVLClient, DeepSeekVLClient
from src.agent.tools import ToolRegistry, build_cv_tools
from src.agent.agent import CVAgent


@pytest.mark.asyncio
async def test_qwen_chat() -> None:
    client = QwenVLClient()
    response = await client.chat([{"role": "user", "content": "hi"}])
    assert response["content"] is not None


@pytest.mark.asyncio
async def test_qwen_image_chat() -> None:
    client = QwenVLClient()
    response = await client.chat_with_image("What is this?", b"fake_image_data")
    assert response["content"] is not None


@pytest.mark.asyncio
async def test_deepseek_chat() -> None:
    client = DeepSeekVLClient()
    response = await client.chat([{"role": "user", "content": "hi"}])
    assert response["content"] is not None


@pytest.mark.asyncio
async def test_tool_registry() -> None:
    from src.models.inference import InferenceOrchestrator
    from src.models.registry import ModelRegistry
    orchestrator = InferenceOrchestrator(ModelRegistry())
    registry = ToolRegistry(orchestrator)
    build_cv_tools(registry)

    specs = registry.get_openai_specs()
    assert len(specs) == 6
    names = {s["function"]["name"] for s in specs}
    assert "detect_objects" in names
    assert "recognize_license_plate" in names


@pytest.mark.asyncio
async def test_agent_analyze() -> None:
    from src.models.inference import InferenceOrchestrator
    from src.models.registry import ModelRegistry, ModelSpec
    from src.models.inference import ModelAdapter

    registry = ModelRegistry()
    registry.register(ModelSpec(model_id="object_detection", name="OD", version="1.0.0"))

    class StubAdapter(ModelAdapter):
        async def predict(self, spec, inp):
            return {"objects": [{"label": "car", "confidence": 0.95}]}
    from src.models.inference import InferenceOrchestrator
    orchestrator = InferenceOrchestrator(registry)
    orchestrator.register_adapter("onnx", StubAdapter())
    tool_registry = ToolRegistry(orchestrator)
    build_cv_tools(tool_registry)

    client = QwenVLClient()
    agent = CVAgent(client, tool_registry)
    result = await agent.analyze({"scene": "traffic intersection"})
    assert result["path"] == "agent"
    assert "latency_ms" in result


@pytest.mark.asyncio
async def test_agent_orchestrator_routes_to_fast_path_first() -> None:
    from src.models.inference import InferenceOrchestrator
    from src.models.registry import ModelRegistry
    from src.pipeline.dag import DAGDefinition, DAGNode, NodeType
    from src.pipeline.executor import DAGExecutor
    from src.pipeline.registry import PipelineRegistry
    from src.routing.fast_path import FastPathHandler
    from src.routing.scene_router import SceneRouter
    from src.routing.matchers import camera_id_matcher
    from src.agent.orchestrator import AgentOrchestrator

    router = SceneRouter()
    registry = PipelineRegistry()
    executor = DAGExecutor()

    dag = DAGDefinition(name="test_pipeline")
    dag.add_node(DAGNode(node_id="detect", node_type=NodeType.MODEL_INFERENCE))
    executor.register_handler(NodeType.MODEL_INFERENCE, lambda ctx, inp: {"ok": True})
    registry.register("test_pipeline", dag)
    router.add_matcher(camera_id_matcher({"cam-01": "test_pipeline"}))

    fast_path = FastPathHandler(router, registry, executor)
    inference = InferenceOrchestrator(ModelRegistry())
    agent = CVAgent(QwenVLClient(), ToolRegistry(inference))
    orchestrator = AgentOrchestrator(fast_path, agent, inference)

    result = await orchestrator.process({"camera_id": "cam-01"})
    assert result["path"] == "fast"
