from fastapi.testclient import TestClient

from src.api.app import app
from src.models.registry import ModelRegistry, ModelSpec, ModelStatus
from src.api.routes import models as models_route

client = TestClient(app)


def _init_registry() -> None:
    registry = ModelRegistry()
    registry.register(ModelSpec(model_id="detector", name="Detector", version="1.0.0", backend="onnx"))
    registry.register(ModelSpec(model_id="recognizer", name="Recognizer", version="2.0.0", backend="onnx", status=ModelStatus.OFFLINE))
    models_route.init_registry(registry)


def _get_token() -> str:
    resp = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"})
    return resp.json()["access_token"]


def test_model_stats_requires_auth() -> None:
    resp = client.get("/api/v1/models/detector/stats")
    assert resp.status_code == 401


def test_model_stats_returns_data() -> None:
    _init_registry()
    token = _get_token()
    resp = client.get("/api/v1/models/detector/stats", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["model_id"] == "detector"
    assert "requests_total" in data
    assert "latency" in data
    assert "avg_ms" in data["latency"]


def test_model_stats_unknown_model() -> None:
    _init_registry()
    token = _get_token()
    resp = client.get("/api/v1/models/unknown/stats", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 404


def test_model_stats_structure() -> None:
    _init_registry()
    token = _get_token()
    resp = client.get("/api/v1/models/detector/stats", headers={"Authorization": f"Bearer {token}"})
    data = resp.json()
    assert isinstance(data["requests_total"], int)
    assert isinstance(data["latency"]["avg_ms"], float)
    assert "p50" in data["latency"]
    assert "p95" in data["latency"]
    assert "p99" in data["latency"]
