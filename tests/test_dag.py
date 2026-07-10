import pytest

from src.pipeline.dag import DAGDefinition, DAGNode, NodeType
from src.pipeline.executor import DAGExecutor


@pytest.mark.asyncio
async def test_simple_dag() -> None:
    dag = DAGDefinition(name="test")
    dag.add_node(DAGNode(node_id="detect", node_type=NodeType.MODEL_INFERENCE))
    dag.add_node(DAGNode(
        node_id="output", node_type=NodeType.OUTPUT, depends_on=["detect"]
    ))
    dag.entry_nodes = ["detect"]
    dag.output_node = "output"

    assert dag.validate()

    executor = DAGExecutor()
    executor.register_handler(NodeType.MODEL_INFERENCE, lambda ctx, inp, cfg: {"objects": 3})
    executor.register_handler(NodeType.OUTPUT, lambda ctx, inp, cfg: inp)

    results = await executor.execute(dag, {})
    assert "detect" in results
    assert results["detect"] == {"objects": 3}


@pytest.mark.asyncio
async def test_dag_with_condition() -> None:
    dag = DAGDefinition(name="cond_test")
    dag.add_node(DAGNode(node_id="classify", node_type=NodeType.MODEL_INFERENCE))
    dag.add_node(DAGNode(
        node_id="condition", node_type=NodeType.CONDITION, depends_on=["classify"]
    ))
    dag.add_node(DAGNode(
        node_id="output", node_type=NodeType.OUTPUT, depends_on=["condition"]
    ))
    dag.entry_nodes = ["classify"]

    executor = DAGExecutor()
    executor.register_handler(NodeType.MODEL_INFERENCE, lambda ctx, inp, cfg: {"label": "car"})
    executor.register_handler(NodeType.CONDITION, lambda ctx, inp, cfg: inp)
    executor.register_handler(NodeType.OUTPUT, lambda ctx, inp, cfg: inp)

    results = await executor.execute(dag, {})
    assert results["classify"]["label"] == "car"


def test_dag_validation_fails_on_missing_dep() -> None:
    dag = DAGDefinition(name="bad")
    dag.add_node(DAGNode(
        node_id="out", node_type=NodeType.OUTPUT, depends_on=["missing"]
    ))
    assert not dag.validate()
