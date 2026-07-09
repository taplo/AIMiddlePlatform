from fastapi.testclient import TestClient

from src.api.app import app
from src.api.routes.admin.pipelines import init_pipeline_registry
from src.pipeline.dag import DAGDefinition, DAGNode, NodeType
from src.pipeline.registry import PipelineRegistry

client = TestClient(app)

def _token():
    resp = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"})
    return resp.json()["access_token"]

_headers = {}

def _init_registry():
    registry = PipelineRegistry()
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
    init_pipeline_registry(registry)

def setup_module():
    global _headers
    _init_registry()
    _headers = {"Authorization": f"Bearer {_token()}"}


def test_list_pipelines():
    resp = client.get("/api/v1/pipelines", headers=_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "pipelines" in data
    assert len(data["pipelines"]) >= 5


def test_get_pipeline_dag():
    resp = client.get("/api/v1/pipelines/object_detection", headers=_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "object_detection"
    assert "nodes" in data
    assert "entry_nodes" in data


def test_get_pipeline_not_found():
    resp = client.get("/api/v1/pipelines/nonexistent", headers=_headers)
    assert resp.status_code == 404


def test_create_pipeline():
    payload = {
        "name": "test_pipeline",
        "nodes": [
            {"node_id": "detect", "node_type": "model_inference", "config": {"model": "object_detection"}, "depends_on": []},
        ],
        "entry_nodes": ["detect"],
        "output_node": "detect",
    }
    resp = client.post("/api/v1/pipelines", json=payload, headers=_headers)
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    # verify it was created
    resp2 = client.get("/api/v1/pipelines/test_pipeline", headers=_headers)
    assert resp2.status_code == 200


def test_create_pipeline_duplicate():
    payload = {
        "name": "test_pipeline",
        "nodes": [
            {"node_id": "detect", "node_type": "model_inference", "config": {"model": "object_detection"}, "depends_on": []},
        ],
        "entry_nodes": ["detect"],
        "output_node": "detect",
    }
    resp = client.post("/api/v1/pipelines", json=payload, headers=_headers)
    assert resp.status_code == 409


def test_create_pipeline_invalid_dag():
    payload = {
        "name": "invalid_dag",
        "nodes": [
            {"node_id": "a", "node_type": "model_inference", "config": {}, "depends_on": ["b"]},
        ],
        "entry_nodes": ["a"],
        "output_node": "a",
    }
    resp = client.post("/api/v1/pipelines", json=payload, headers=_headers)
    assert resp.status_code == 400


def test_update_pipeline():
    payload = {
        "nodes": [
            {"node_id": "detect", "node_type": "model_inference", "config": {"model": "face_recognition"}, "depends_on": []},
        ],
        "entry_nodes": ["detect"],
        "output_node": "detect",
    }
    resp = client.put("/api/v1/pipelines/test_pipeline", json=payload, headers=_headers)
    assert resp.status_code == 200
    resp2 = client.get("/api/v1/pipelines/test_pipeline", headers=_headers)
    nodes = resp2.json()["nodes"]
    assert nodes["detect"]["config"]["model"] == "face_recognition"


def test_delete_pipeline():
    resp = client.delete("/api/v1/pipelines/test_pipeline", headers=_headers)
    assert resp.status_code == 200
    resp2 = client.get("/api/v1/pipelines/test_pipeline", headers=_headers)
    assert resp2.status_code == 404
