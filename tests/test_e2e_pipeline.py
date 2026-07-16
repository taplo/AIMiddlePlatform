import pytest

from src.agent.agent import CVAgent
from src.agent.client import QwenVLClient
from src.agent.orchestrator import AgentOrchestrator
from src.agent.tools import ToolRegistry, build_cv_tools
from src.models.inference import InferenceOrchestrator, ModelAdapter
from src.models.registry import ModelRegistry, ModelSpec
from src.pipeline.dag import DAGDefinition, DAGNode, NodeType
from src.pipeline.executor import DAGExecutor
from src.pipeline.registry import PipelineRegistry
from src.routing.fast_path import FastPathHandler
from src.routing.matchers import camera_id_matcher, scene_type_matcher
from src.routing.scene_router import SceneRouter


class StubAdapter(ModelAdapter):
    async def predict(self, spec, input_data):
        return {"prediction": "stub_ok", "model_id": spec.model_id}


def _build_inference() -> tuple[ModelRegistry, InferenceOrchestrator]:
    registry = ModelRegistry()
    registry.register(ModelSpec(model_id="object_detection", name="OD", version="1.0.0"))
    registry.register(ModelSpec(model_id="license_plate", name="LP", version="1.0.0"))
    registry.register(ModelSpec(model_id="face_recognition", name="FR", version="1.0.0"))
    orchestrator = InferenceOrchestrator(registry)
    orchestrator.register_adapter("onnx", StubAdapter())
    return registry, orchestrator


def _build_fast_path() -> tuple[SceneRouter, PipelineRegistry, DAGExecutor, FastPathHandler]:
    router = SceneRouter()
    registry = PipelineRegistry()
    executor = DAGExecutor()

    dag = DAGDefinition(name="plate_dag")
    dag.add_node(DAGNode(node_id="detect", node_type=NodeType.MODEL_INFERENCE))
    executor.register_handler(NodeType.MODEL_INFERENCE, lambda ctx, inp, cfg: {"plate": "京A12345"})
    registry.register("plate_recognition", dag)

    router.add_matcher(camera_id_matcher({"cam-plate-01": "plate_recognition"}))
    router.add_matcher(scene_type_matcher({"parking_lot": "plate_recognition"}))

    handler = FastPathHandler(router, registry, executor)
    return router, registry, executor, handler


@pytest.mark.asyncio
async def test_e2e_fast_path_hit_by_camera_id() -> None:
    import httpx
    _, _, _, fast_path = _build_fast_path()
    _, infer = _build_inference()
    tool_registry = ToolRegistry(infer)
    build_cv_tools(tool_registry)
    mock_transport = httpx.MockTransport(lambda req: httpx.Response(200, json={
        "choices": [{"message": {"content": '{"scene_type": "parking_lot", "objects": [], "anomalies": [], "summary": "plate detected"}', "role": "assistant"}}]
    }))
    agent = CVAgent(QwenVLClient(http_client=httpx.AsyncClient(transport=mock_transport)), tool_registry)
    orchestrator = AgentOrchestrator(fast_path, agent, infer)

    result = await orchestrator.process({"camera_id": "cam-plate-01"})
    assert result["path"] == "agent"
    assert "latency_ms" in result


@pytest.mark.asyncio
async def test_e2e_fast_path_hit_by_scene_type() -> None:
    import httpx
    _, _, _, fast_path = _build_fast_path()
    _, infer = _build_inference()
    tool_registry = ToolRegistry(infer)
    build_cv_tools(tool_registry)
    mock_transport = httpx.MockTransport(lambda req: httpx.Response(200, json={
        "choices": [{"message": {"content": '{"scene_type": "parking_lot", "objects": [], "anomalies": [], "summary": "plate detected"}', "role": "assistant"}}]
    }))
    agent = CVAgent(QwenVLClient(http_client=httpx.AsyncClient(transport=mock_transport)), tool_registry)
    orchestrator = AgentOrchestrator(fast_path, agent, infer)

    result = await orchestrator.process({"scene_type": "parking_lot", "camera_id": "cam-99"})
    assert result["path"] == "agent"


@pytest.mark.asyncio
async def test_e2e_fast_path_miss_then_agent() -> None:
    import httpx
    _, infer = _build_inference()
    tool_registry = ToolRegistry(infer)
    build_cv_tools(tool_registry)
    mock_transport = httpx.MockTransport(lambda req: httpx.Response(200, json={
        "choices": [{"message": {"content": '{"scene_type": "unknown", "objects": [], "anomalies": [], "summary": "no match"}', "role": "assistant"}}]
    }))
    agent = CVAgent(QwenVLClient(http_client=httpx.AsyncClient(transport=mock_transport)), tool_registry)

    router = SceneRouter()
    registry = PipelineRegistry()
    executor = DAGExecutor()
    fast_path = FastPathHandler(router, registry, executor)
    orchestrator = AgentOrchestrator(fast_path, agent, infer)

    result = await orchestrator.process({"scene_type": "unknown_scene", "camera_id": "cam-new"})
    assert result["path"] == "agent"
    assert "latency_ms" in result


@pytest.mark.asyncio
async def test_e2e_fast_path_with_model_inference() -> None:
    import httpx
    router = SceneRouter()
    registry = PipelineRegistry()
    executor = DAGExecutor()
    model_reg, infer = _build_inference()

    pipeline_dag = DAGDefinition(name="object_detection_pipeline")
    pipeline_dag.add_node(DAGNode(node_id="inference", node_type=NodeType.MODEL_INFERENCE))
    executor.register_handler(
        NodeType.MODEL_INFERENCE,
        lambda ctx, inp, cfg: {"output": ctx.get("model_id", "unknown")},
    )
    registry.register("obj_detect", pipeline_dag)
    router.add_matcher(camera_id_matcher({"cam-obj-01": "obj_detect"}))

    fast_path = FastPathHandler(router, registry, executor)
    tool_registry = ToolRegistry(infer)
    mock_transport = httpx.MockTransport(lambda req: httpx.Response(200, json={
        "choices": [{"message": {"content": '{"scene_type": "office", "objects": [], "anomalies": [], "summary": "done"}', "role": "assistant"}}]
    }))
    agent = CVAgent(QwenVLClient(http_client=httpx.AsyncClient(transport=mock_transport)), tool_registry)
    orchestrator = AgentOrchestrator(fast_path, agent, infer)

    result = await orchestrator.process({"camera_id": "cam-obj-01", "model_id": "yolov8"})
    assert result["path"] == "agent"


@pytest.mark.asyncio
async def test_e2e_agent_with_image_routes_correctly() -> None:
    import httpx
    router = SceneRouter()
    pipeline_registry = PipelineRegistry()
    executor = DAGExecutor()
    _, infer = _build_inference()

    fast_path = FastPathHandler(router, pipeline_registry, executor)
    tool_registry = ToolRegistry(infer)
    build_cv_tools(tool_registry)
    mock_transport = httpx.MockTransport(lambda req: httpx.Response(200, json={
        "choices": [{"message": {"content": '{"scene_type": "office", "objects": [], "anomalies": [], "summary": "empty"}', "role": "assistant"}}]
    }))
    agent = CVAgent(QwenVLClient(http_client=httpx.AsyncClient(transport=mock_transport)), tool_registry)
    orchestrator = AgentOrchestrator(fast_path, agent, infer)

    result = await orchestrator.process(
        {"scene_type": "unknown"},
        image_data=b"fake_jpeg_bytes",
    )
    assert result["path"] == "agent"


@pytest.mark.asyncio
async def test_e2e_orchestrator_standalone_inference() -> None:
    model_reg, infer = _build_inference()

    result = await infer.infer("object_detection", {"image": "data"})
    assert result["model_id"] == "object_detection"
    assert result["version"] == "1.0.0"
    assert result["output"]["prediction"] == "stub_ok"
    assert "latency_ms" in result


@pytest.mark.asyncio
async def test_e2e_parallel_inference() -> None:
    _, infer = _build_inference()

    results = await infer.infer_parallel([
        ("object_detection", {"image": "a"}),
        ("license_plate", {"image": "b"}),
        ("face_recognition", {"image": "c"}),
    ])
    assert len(results) == 3
    assert all(r["model_id"] in ("object_detection", "license_plate", "face_recognition") for r in results)


@pytest.mark.asyncio
async def test_e2e_full_pipeline_includes_latency_and_path() -> None:
    import httpx
    _, _, _, fast_path = _build_fast_path()
    _, infer = _build_inference()
    tool_registry = ToolRegistry(infer)
    mock_transport = httpx.MockTransport(lambda req: httpx.Response(200, json={
        "choices": [{"message": {"content": '{"scene_type": "parking_lot", "objects": [], "anomalies": [], "summary": "done"}', "role": "assistant"}}]
    }))
    agent = CVAgent(QwenVLClient(http_client=httpx.AsyncClient(transport=mock_transport)), tool_registry)
    orchestrator = AgentOrchestrator(fast_path, agent, infer)

    result = await orchestrator.process({"camera_id": "cam-plate-01"})
    assert "path" in result
    assert "latency_ms" in result
    assert result["latency_ms"] >= 0
