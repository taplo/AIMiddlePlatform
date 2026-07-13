import pytest

from src.pipeline.dag import DAGDefinition, DAGNode, NodeType
from src.pipeline.executor import DAGExecutor


@pytest.mark.asyncio
async def test_executor_async_handler() -> None:
    dag = DAGDefinition(name="async_test")
    dag.add_node(DAGNode(node_id="step1", node_type=NodeType.CONDITION))
    dag.add_node(DAGNode(
        node_id="output", node_type=NodeType.OUTPUT, depends_on=["step1"]
    ))
    dag.entry_nodes = ["step1"]

    executor = DAGExecutor()

    async def async_handler(ctx, inp, cfg):
        return {"from_async": True}

    executor.register_handler(NodeType.CONDITION, async_handler)
    executor.register_handler(NodeType.OUTPUT, lambda ctx, inp, cfg: inp)

    results = await executor.execute(dag, {})
    assert results["step1"]["from_async"] is True


@pytest.mark.asyncio
async def test_executor_mixed_handlers() -> None:
    dag = DAGDefinition(name="mixed_test")
    dag.add_node(DAGNode(node_id="sync_step", node_type=NodeType.MODEL_INFERENCE))
    dag.add_node(DAGNode(
        node_id="async_step", node_type=NodeType.VERIFY, depends_on=["sync_step"]
    ))
    dag.entry_nodes = ["sync_step"]

    executor = DAGExecutor()
    executor.register_handler(NodeType.MODEL_INFERENCE, lambda ctx, inp, cfg: {"detections": [{"label": "car"}]})

    async def async_verify(ctx, inp, cfg):
        return {"verified": True, "detections": inp.get("detections", [])}

    executor.register_handler(NodeType.VERIFY, async_verify)

    results = await executor.execute(dag, {})
    assert results["sync_step"]["detections"][0]["label"] == "car"
    assert results["async_step"]["verified"] is True


@pytest.mark.asyncio
async def test_executor_sync_handler_still_works() -> None:
    dag = DAGDefinition(name="sync_test")
    dag.add_node(DAGNode(node_id="detect", node_type=NodeType.MODEL_INFERENCE))
    dag.entry_nodes = ["detect"]

    executor = DAGExecutor()
    executor.register_handler(NodeType.MODEL_INFERENCE, lambda ctx, inp, cfg: {"result": "ok"})

    results = await executor.execute(dag, {})
    assert results["detect"]["result"] == "ok"
