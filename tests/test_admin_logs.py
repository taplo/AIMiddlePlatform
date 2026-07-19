import logging

from fastapi.testclient import TestClient

from src.api.app import app
from src.monitoring.log_buffer import clear_logs, init_log_buffer

client = TestClient(app)

def _token():
    resp = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"})
    return resp.json()["access_token"]

_headers = {}

def setup_module():
    global _headers
    _headers = {"Authorization": f"Bearer {_token()}"}
    clear_logs()
    init_log_buffer(maxlen=200)


def test_get_logs_empty():
    resp = client.get("/api/v1/logs", headers=_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "logs" in data
    assert "total" in data


def test_get_logs_with_entries():
    logging.getLogger("test_logs_api").warning("test warning message")
    logging.getLogger("test_logs_api").info("test info message")
    resp = client.get("/api/v1/logs", headers=_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 2


def test_get_logs_filter_level():
    resp = client.get("/api/v1/logs?level=WARNING", headers=_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert all(e["level"] == "WARNING" for e in data["logs"])


def test_get_logs_search():
    resp = client.get("/api/v1/logs?q=warning", headers=_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["logs"]) >= 1
