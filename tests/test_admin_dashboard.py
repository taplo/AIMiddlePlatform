import pytest
from fastapi.testclient import TestClient

from src.api.app import app

client = TestClient(app)


def _get_token() -> str:
    resp = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"})
    return resp.json()["access_token"]


def test_dashboard_stats_structure() -> None:
    token = _get_token()
    resp = client.get("/api/v1/system/stats", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert "qps" in data
    assert "cameras" in data
    assert "models" in data
    assert "latency" in data


def test_dashboard_stats_types() -> None:
    token = _get_token()
    resp = client.get("/api/v1/system/stats", headers={"Authorization": f"Bearer {token}"})
    data = resp.json()
    assert isinstance(data["qps"], float) or isinstance(data["qps"], int)
    assert isinstance(data["cameras"]["total"], int)
    assert isinstance(data["cameras"]["online"], int)
    assert isinstance(data["models"]["total"], int)
    assert isinstance(data["models"]["active"], int)
    assert "p50" in data["latency"]
    assert "p95" in data["latency"]
    assert "p99" in data["latency"]
