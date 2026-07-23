from fastapi.testclient import TestClient

from src.api.app import app

client = TestClient(app)


def _get_token() -> str:
    resp = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"})
    return resp.json()["access_token"]


def test_list_channels_returns_defaults(tmp_path):
    test_file = tmp_path / "channels.json"
    import src.api.routes.admin.notifications as mod
    original = mod.CHANNELS_FILE
    try:
        mod.CHANNELS_FILE = str(test_file)
        token = _get_token()
        resp = client.get("/api/v1/admin/notifications", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 3
        assert data[0]["name"] == "DingTalk"
        assert data[1]["name"] == "WeChat Work"
        assert data[2]["name"] == "Feishu"
    finally:
        mod.CHANNELS_FILE = original


def test_update_channel_persists(tmp_path):
    test_file = tmp_path / "channels.json"
    import src.api.routes.admin.notifications as mod
    original = mod.CHANNELS_FILE
    try:
        mod.CHANNELS_FILE = str(test_file)
        token = _get_token()
        headers = {"Authorization": f"Bearer {token}"}
        resp = client.put(
            "/api/v1/admin/notifications/DingTalk",
            json={"enabled": True, "config": {"webhook_url": "https://oapi.dingtalk.com/test"}},
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        dingtalk = next(c for c in data if c["name"] == "DingTalk")
        assert dingtalk["enabled"] is True
        assert dingtalk["config"]["webhook_url"] == "https://oapi.dingtalk.com/test"

        resp2 = client.get("/api/v1/admin/notifications", headers=headers)
        data2 = resp2.json()
        dingtalk2 = next(c for c in data2 if c["name"] == "DingTalk")
        assert dingtalk2["enabled"] is True
    finally:
        mod.CHANNELS_FILE = original


def test_update_channel_not_found(tmp_path):
    import src.api.routes.admin.notifications as mod
    original = mod.CHANNELS_FILE
    try:
        mod.CHANNELS_FILE = str(tmp_path / "channels.json")
        token = _get_token()
        resp = client.put(
            "/api/v1/admin/notifications/NonExistent",
            json={"enabled": True, "config": {}},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 404
    finally:
        mod.CHANNELS_FILE = original


def test_list_channels_without_auth():
    resp = client.get("/api/v1/admin/notifications")
    assert resp.status_code == 401
