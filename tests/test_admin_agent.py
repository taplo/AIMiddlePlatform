from fastapi.testclient import TestClient

from src.api.app import app

client = TestClient(app)


def _get_token() -> str:
    resp = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"})
    return resp.json()["access_token"]


def test_get_agent_config_structure() -> None:
    token = _get_token()
    resp = client.get("/api/v1/agent/config", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert "llm" in data
    assert "system_prompt" in data
    assert "thresholds" in data
    assert "routing_rules" in data


def test_save_and_retrieve_agent_config() -> None:
    token = _get_token()
    payload = {
        "llm": {"provider": "Qwen", "url": "http://test:8000", "api_key": "sk-test"},
        "system_prompt": "You are a test assistant.",
        "thresholds": {"entrance": 0.8, "street": 0.6},
        "routing_rules": [{"scene_id": "test_scene", "pipeline": "object_detection"}],
    }
    save_resp = client.post("/api/v1/agent/config", json=payload, headers={"Authorization": f"Bearer {token}"})
    assert save_resp.status_code == 200
    get_resp = client.get("/api/v1/agent/config", headers={"Authorization": f"Bearer {token}"})
    data = get_resp.json()
    assert data["llm"]["provider"] == "Qwen"
    assert data["system_prompt"] == "You are a test assistant."
    assert data["thresholds"]["entrance"] == 0.8
    assert len(data["routing_rules"]) == 1


def test_get_config_returns_defaults() -> None:
    token = _get_token()
    resp = client.get("/api/v1/agent/config", headers={"Authorization": f"Bearer {token}"})
    data = resp.json()
    assert isinstance(data["routing_rules"], list)
    assert isinstance(data["thresholds"], dict)
