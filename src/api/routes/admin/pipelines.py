from fastapi import APIRouter, HTTPException

from src.pipeline.dag import DAGDefinition, DAGNode, NodeType
from src.pipeline.registry import PipelineRegistry

router = APIRouter(prefix="/api/v1/pipelines", tags=["admin-pipelines"])

_registry: PipelineRegistry | None = None


def init_pipeline_registry(registry: PipelineRegistry) -> None:
    global _registry
    _registry = registry


@router.get("")
async def list_pipelines() -> dict:
    if _registry is None:
        return {"pipelines": []}
    names = _registry.list()
    result = []
    for name in names:
        dag = _registry.get(name)
        if dag:
            result.append({
                "name": dag.name,
                "node_count": len(dag.nodes),
                "entry_nodes": dag.entry_nodes,
                "output_node": dag.output_node,
            })
    return {"pipelines": result}


@router.get("/{name}")
async def get_pipeline_dag(name: str) -> dict:
    if _registry is None:
        raise HTTPException(404, "Registry not initialized")
    dag = _registry.get(name)
    if dag is None:
        raise HTTPException(404, f"Pipeline '{name}' not found")
    return {
        "name": dag.name,
        "nodes": {nid: {"node_id": n.node_id, "node_type": n.node_type.value, "config": n.config, "depends_on": n.depends_on} for nid, n in dag.nodes.items()},
        "entry_nodes": dag.entry_nodes,
        "output_node": dag.output_node,
    }


@router.post("")
async def create_pipeline(body: dict) -> dict:
    if _registry is None:
        raise HTTPException(500, "Registry not initialized")
    name = body.get("name", "")
    if _registry.get(name) is not None:
        raise HTTPException(409, f"Pipeline '{name}' already exists")
    dag = _build_dag(body)
    _registry.register(name, dag)
    return {"ok": True}


@router.put("/{name}")
async def update_pipeline(name: str, body: dict) -> dict:
    if _registry is None:
        raise HTTPException(500, "Registry not initialized")
    if _registry.get(name) is None:
        raise HTTPException(404, f"Pipeline '{name}' not found")
    _registry.unregister(name)
    dag = _build_dag({**body, "name": name})
    _registry.register(name, dag)
    return {"ok": True}


@router.delete("/{name}")
async def delete_pipeline(name: str) -> dict:
    if _registry is None:
        raise HTTPException(500, "Registry not initialized")
    if _registry.get(name) is None:
        raise HTTPException(404, f"Pipeline '{name}' not found")
    _registry.unregister(name)
    return {"ok": True}


def _build_dag(body: dict) -> DAGDefinition:
    name = body.get("name", "")
    nodes_data = body.get("nodes", [])
    entry_nodes = body.get("entry_nodes", [])
    output_node = body.get("output_node", "")

    dag = DAGDefinition(name=name, entry_nodes=entry_nodes, output_node=output_node)
    for nd in nodes_data:
        try:
            ntype = NodeType(nd["node_type"])
        except ValueError:
            raise HTTPException(400, f"Invalid node_type: {nd['node_type']}")
        node = DAGNode(
            node_id=nd["node_id"],
            node_type=ntype,
            config=nd.get("config", {}),
            depends_on=nd.get("depends_on", []),
        )
        dag.add_node(node)
    if not dag.validate():
        raise HTTPException(400, "Invalid DAG: dependency references non-existent node")
    return dag
