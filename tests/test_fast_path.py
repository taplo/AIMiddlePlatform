import pytest

from src.pipeline.dag import DAGDefinition, DAGNode, NodeType
from src.pipeline.executor import DAGExecutor
from src.pipeline.registry import PipelineRegistry
from src.routing.fast_path import FastPathHandler
from src.routing.scene_router import SceneRouter


@pytest.mark.asyncio
async def test_fast_path_integration() -> None:
    router = SceneRouter()
    registry = PipelineRegistry()
    executor = DAGExecutor()

    dag = DAGDefinition(name="plate_recognition")
    dag.add_node(DAGNode(node_id="detect", node_type=NodeType.MODEL_INFERENCE))
    executor.register_handler(NodeType.MODEL_INFERENCE, lambda ctx, inp, cfg: {"plate": "京A12345"})

    registry.register("plate_recognition", dag)
    router.register_route("test_hash", "plate_recognition")

    handler = FastPathHandler(router, registry, executor)
    result = await handler.process({"scene": "unknown"})

    assert result is None


@pytest.mark.asyncio
async def test_fast_path_hit() -> None:
    router = SceneRouter()
    registry = PipelineRegistry()
    executor = DAGExecutor()

    dag = DAGDefinition(name="detection")
    dag.add_node(DAGNode(node_id="detect", node_type=NodeType.MODEL_INFERENCE))
    executor.register_handler(NodeType.MODEL_INFERENCE, lambda ctx, inp, cfg: {"objects": 5})

    registry.register("detection", dag)
    from src.routing.matchers import camera_id_matcher
    router.add_matcher(camera_id_matcher({"cam-01": "detection"}))

    handler = FastPathHandler(router, registry, executor)
    result = await handler.process({"camera_id": "cam-01"})

    assert result is not None
    assert result["path"] == "fast"
    assert result["pipeline"] == "detection"
    assert "latency_ms" in result
