import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.api import deps as api_deps
from src.api.app import app
from src.core.database import init_db

pytestmark = pytest.mark.usefixtures('_setup_db')
client = TestClient(app)


def _get_token() -> str:
    resp = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"})
    return resp.json()["access_token"]


@pytest.fixture
async def _setup_db():
    engine = await init_db("sqlite+aiosqlite://")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    prev = api_deps._session_factory
    api_deps.init_session_factory(factory)
    yield
    api_deps.init_session_factory(prev)


def _auth_headers() -> dict:
    return {"Authorization": f"Bearer {_get_token()}"}


class TestRuleCRUD:
    def test_create_rule(self) -> None:
        resp = client.post("/api/v1/admin/rules", json={
            "name": "test_rule",
            "rule_type": "count_threshold",
            "config": '{"min": 0, "max": 5}',
            "description": "A test rule",
        }, headers=_auth_headers())
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "test_rule"
        assert data["rule_type"] == "count_threshold"
        assert data["enabled"] is True
        assert data["description"] == "A test rule"
        assert "id" in data

    def test_create_rule_duplicate_name(self) -> None:
        client.post("/api/v1/admin/rules", json={
            "name": "dup_rule",
            "rule_type": "count_threshold",
            "config": "{}",
        }, headers=_auth_headers())
        resp = client.post("/api/v1/admin/rules", json={
            "name": "dup_rule",
            "rule_type": "loitering",
            "config": "{}",
        }, headers=_auth_headers())
        assert resp.status_code == 409

    def test_get_rule(self) -> None:
        create_resp = client.post("/api/v1/admin/rules", json={
            "name": "get_test",
            "rule_type": "region_intrusion",
            "config": '{"zone": "A"}',
        }, headers=_auth_headers())
        rule_id = create_resp.json()["id"]
        resp = client.get(f"/api/v1/admin/rules/{rule_id}", headers=_auth_headers())
        assert resp.status_code == 200
        assert resp.json()["name"] == "get_test"

    def test_get_rule_not_found(self) -> None:
        resp = client.get("/api/v1/admin/rules/99999", headers=_auth_headers())
        assert resp.status_code == 404

    def test_update_rule(self) -> None:
        create_resp = client.post("/api/v1/admin/rules", json={
            "name": "update_test",
            "rule_type": "count_threshold",
            "config": "{}",
        }, headers=_auth_headers())
        rule_id = create_resp.json()["id"]
        resp = client.put(f"/api/v1/admin/rules/{rule_id}", json={
            "description": "Updated description",
            "enabled": False,
        }, headers=_auth_headers())
        assert resp.status_code == 200
        data = resp.json()
        assert data["description"] == "Updated description"
        assert data["enabled"] is False

    def test_update_rule_not_found(self) -> None:
        resp = client.put("/api/v1/admin/rules/99999", json={"name": "nope"}, headers=_auth_headers())
        assert resp.status_code == 404

    def test_delete_rule_soft(self) -> None:
        create_resp = client.post("/api/v1/admin/rules", json={
            "name": "delete_test",
            "rule_type": "loitering",
            "config": "{}",
        }, headers=_auth_headers())
        rule_id = create_resp.json()["id"]
        resp = client.delete(f"/api/v1/admin/rules/{rule_id}", headers=_auth_headers())
        assert resp.status_code == 200
        get_resp = client.get(f"/api/v1/admin/rules/{rule_id}", headers=_auth_headers())
        assert get_resp.json()["enabled"] is False

    def test_delete_rule_not_found(self) -> None:
        resp = client.delete("/api/v1/admin/rules/99999", headers=_auth_headers())
        assert resp.status_code == 404

    def test_list_rules(self) -> None:
        client.post("/api/v1/admin/rules", json={"name": "list_a", "rule_type": "count_threshold", "config": "{}"}, headers=_auth_headers())
        client.post("/api/v1/admin/rules", json={"name": "list_b", "rule_type": "region_intrusion", "config": "{}"}, headers=_auth_headers())
        resp = client.get("/api/v1/admin/rules", headers=_auth_headers())
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 2
        assert len(data["items"]) >= 2
        assert "page" in data

    def test_list_rules_filter_by_type(self) -> None:
        client.post("/api/v1/admin/rules", json={"name": "filter_type", "rule_type": "count_threshold", "config": "{}"}, headers=_auth_headers())
        resp = client.get("/api/v1/admin/rules?rule_type=count_threshold", headers=_auth_headers())
        assert resp.status_code == 200
        assert all(r["rule_type"] == "count_threshold" for r in resp.json()["items"])

    def test_list_rules_filter_by_enabled(self) -> None:
        client.post("/api/v1/admin/rules", json={"name": "filter_enabled", "rule_type": "count_threshold", "config": "{}", "enabled": True}, headers=_auth_headers())
        resp = client.get("/api/v1/admin/rules?enabled=true", headers=_auth_headers())
        assert resp.status_code == 200
        assert all(r["enabled"] is True for r in resp.json()["items"])

    def test_create_rule_missing_required(self) -> None:
        resp = client.post("/api/v1/admin/rules", json={"name": ""}, headers=_auth_headers())
        assert resp.status_code == 422


class TestRuleBindingCRUD:
    def _create_rule(self, name: str = "binding_parent") -> int:
        resp = client.post("/api/v1/admin/rules", json={
            "name": name,
            "rule_type": "count_threshold",
            "config": "{}",
        }, headers=_auth_headers())
        return resp.json()["id"]

    def test_create_binding(self) -> None:
        rule_id = self._create_rule()
        resp = client.post("/api/v1/admin/rule-bindings", json={
            "rule_id": rule_id,
            "camera_id": "cam-01",
            "scene_type": "entrance",
            "config_overrides": '{"threshold": 0.8}',
            "priority": 5,
        }, headers=_auth_headers())
        assert resp.status_code == 200
        data = resp.json()
        assert data["rule_id"] == rule_id
        assert data["camera_id"] == "cam-01"
        assert data["scene_type"] == "entrance"
        assert data["priority"] == 5
        assert data["enabled"] is True
        assert "id" in data

    def test_create_binding_duplicate(self) -> None:
        rule_id = self._create_rule("dup_binding")
        client.post("/api/v1/admin/rule-bindings", json={
            "rule_id": rule_id, "camera_id": "cam-dup",
        }, headers=_auth_headers())
        resp = client.post("/api/v1/admin/rule-bindings", json={
            "rule_id": rule_id, "camera_id": "cam-dup",
        }, headers=_auth_headers())
        assert resp.status_code == 409

    def test_create_binding_rule_not_found(self) -> None:
        resp = client.post("/api/v1/admin/rule-bindings", json={
            "rule_id": 99999, "camera_id": "cam-x",
        }, headers=_auth_headers())
        assert resp.status_code == 404

    def test_get_binding(self) -> None:
        rule_id = self._create_rule("get_binding")
        create_resp = client.post("/api/v1/admin/rule-bindings", json={
            "rule_id": rule_id, "camera_id": "cam-get",
        }, headers=_auth_headers())
        binding_id = create_resp.json()["id"]
        resp = client.get(f"/api/v1/admin/rule-bindings/{binding_id}", headers=_auth_headers())
        assert resp.status_code == 200
        assert resp.json()["camera_id"] == "cam-get"

    def test_get_binding_not_found(self) -> None:
        resp = client.get("/api/v1/admin/rule-bindings/99999", headers=_auth_headers())
        assert resp.status_code == 404

    def test_update_binding(self) -> None:
        rule_id = self._create_rule("update_binding")
        create_resp = client.post("/api/v1/admin/rule-bindings", json={
            "rule_id": rule_id, "camera_id": "cam-upd",
        }, headers=_auth_headers())
        binding_id = create_resp.json()["id"]
        resp = client.put(f"/api/v1/admin/rule-bindings/{binding_id}", json={
            "priority": 10, "enabled": False,
        }, headers=_auth_headers())
        assert resp.status_code == 200
        data = resp.json()
        assert data["priority"] == 10
        assert data["enabled"] is False

    def test_update_binding_not_found(self) -> None:
        resp = client.put("/api/v1/admin/rule-bindings/99999", json={"priority": 1}, headers=_auth_headers())
        assert resp.status_code == 404

    def test_delete_binding_soft(self) -> None:
        rule_id = self._create_rule("delete_binding")
        create_resp = client.post("/api/v1/admin/rule-bindings", json={
            "rule_id": rule_id, "camera_id": "cam-del",
        }, headers=_auth_headers())
        binding_id = create_resp.json()["id"]
        resp = client.delete(f"/api/v1/admin/rule-bindings/{binding_id}", headers=_auth_headers())
        assert resp.status_code == 200
        get_resp = client.get(f"/api/v1/admin/rule-bindings/{binding_id}", headers=_auth_headers())
        assert get_resp.json()["enabled"] is False

    def test_delete_binding_not_found(self) -> None:
        resp = client.delete("/api/v1/admin/rule-bindings/99999", headers=_auth_headers())
        assert resp.status_code == 404

    def test_list_bindings(self) -> None:
        rule_id = self._create_rule("list_bindings")
        client.post("/api/v1/admin/rule-bindings", json={
            "rule_id": rule_id, "camera_id": "cam-l1",
        }, headers=_auth_headers())
        client.post("/api/v1/admin/rule-bindings", json={
            "rule_id": rule_id, "camera_id": "cam-l2",
        }, headers=_auth_headers())
        resp = client.get("/api/v1/admin/rule-bindings", headers=_auth_headers())
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 2
        assert "page" in data

    def test_list_bindings_filter_by_rule_id(self) -> None:
        r1 = self._create_rule("filter_r1")
        r2 = self._create_rule("filter_r2")
        client.post("/api/v1/admin/rule-bindings", json={"rule_id": r1, "camera_id": "cam-f1"}, headers=_auth_headers())
        client.post("/api/v1/admin/rule-bindings", json={"rule_id": r2, "camera_id": "cam-f2"}, headers=_auth_headers())
        resp = client.get(f"/api/v1/admin/rule-bindings?rule_id={r1}", headers=_auth_headers())
        assert resp.status_code == 200
        assert all(b["rule_id"] == r1 for b in resp.json()["items"])

    def test_list_bindings_filter_by_enabled(self) -> None:
        rule_id = self._create_rule("filter_enabled_binding")
        client.post("/api/v1/admin/rule-bindings", json={"rule_id": rule_id, "camera_id": "cam-e1", "enabled": True}, headers=_auth_headers())
        resp = client.get("/api/v1/admin/rule-bindings?enabled=true", headers=_auth_headers())
        assert resp.status_code == 200
        assert all(b["enabled"] is True for b in resp.json()["items"])
