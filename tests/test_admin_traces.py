from fastapi.testclient import TestClient

from src.api.app import app

client = TestClient(app)


def _token():
    resp = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"})
    return resp.json()["access_token"]


_headers = {}


def setup_module():
    global _headers
    _headers = {"Authorization": f"Bearer {_token()}"}


def test_get_traces():
    resp = client.get("/api/v1/traces", headers=_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "traces" in data


def test_get_trace_detail_not_found():
    resp = client.get("/api/v1/traces/nonexistent_trace_id", headers=_headers)
    assert resp.status_code == 404
