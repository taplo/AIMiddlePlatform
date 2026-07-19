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
    assert "total_streams" in data
    assert "active_tasks" in data
    assert "connected" in data
    assert "total_frames_kept" in data


def test_dashboard_stats_types() -> None:
    token = _get_token()
    resp = client.get("/api/v1/system/stats", headers={"Authorization": f"Bearer {token}"})
    data = resp.json()
    assert isinstance(data["total_streams"], int)
    assert isinstance(data["active_tasks"], int)
    assert isinstance(data["connected"], int)
    assert isinstance(data["total_frames_kept"], int)
