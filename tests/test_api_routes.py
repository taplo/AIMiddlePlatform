import pytest
from fastapi.testclient import TestClient

from src.api.app import app
from src.api.routes import models as models_route
from src.models.registry import ModelRegistry, ModelSpec

client = TestClient(app)
_TEST_API_KEY = "sk-test-api-key-old-routes-0987654321"


@pytest.fixture(autouse=True)
def _setup_api_key():
    from src.core.security import get_api_key_store
    store = get_api_key_store()
    store.add_key("test", _TEST_API_KEY, rate_per_second=1000)
    yield


def _headers() -> dict:
    return {"X-API-Key": _TEST_API_KEY}


def test_list_config() -> None:
    resp = client.get("/api/v1/config/", headers=_headers())
    assert resp.status_code == 200
    data = resp.json()
    assert "app" in data


def test_config_section() -> None:
    resp = client.get("/api/v1/config/?section=ingestion", headers=_headers())
    assert resp.status_code == 200
    data = resp.json()
    assert "ingestion" in data
    assert "max_streams" in data["ingestion"]


def test_list_models_empty() -> None:
    resp = client.get("/api/v1/models/", headers=_headers())
    assert resp.status_code == 200
    assert resp.json() == []


def test_register_and_list_models() -> None:
    registry = ModelRegistry()
    registry.register(ModelSpec(model_id="test_m", name="Test", version="1.0.0"))
    models_route.init_registry(registry)

    resp = client.get("/api/v1/models/", headers=_headers())
    assert resp.status_code == 200
    models = resp.json()
    assert len(models) == 1
    assert models[0]["model_id"] == "test_m"


def test_get_specific_model() -> None:
    registry = ModelRegistry()
    registry.register(ModelSpec(model_id="specific", name="Specific", version="2.0.0"))
    models_route.init_registry(registry)

    resp = client.get("/api/v1/models/specific", headers=_headers())
    assert resp.status_code == 200
    assert resp.json()["version"] == "2.0.0"


def test_get_nonexistent_model() -> None:
    registry = ModelRegistry()
    models_route.init_registry(registry)

    resp = client.get("/api/v1/models/nonexistent", headers=_headers())
    assert resp.status_code == 404


def test_active_models() -> None:
    registry = ModelRegistry()
    from src.models.registry import ModelStatus
    registry.register(ModelSpec(model_id="m1", name="M1", version="1.0.0"))
    registry.register(ModelSpec(model_id="m2", name="M2", version="1.0.0",
                                status=ModelStatus.OFFLINE))
    models_route.init_registry(registry)

    resp = client.get("/api/v1/models/active", headers=_headers())
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_routing_add_route() -> None:
    from src.api.routes.routing import init_router
    from src.routing.scene_router import SceneRouter

    router = SceneRouter()
    init_router(router)

    resp = client.post("/api/v1/routing/routes", json={"scene_id": "test", "pipeline": "p1"}, headers=_headers())
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


def test_routing_delete_route() -> None:
    from src.api.routes.routing import init_router
    from src.routing.scene_router import SceneRouter

    router = SceneRouter()
    router.register_route("del_me", "p1")
    init_router(router)

    resp = client.delete("/api/v1/routing/routes/del_me", headers=_headers())
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


def test_analyze_ping() -> None:
    resp = client.get("/api/v1/analyze/ping")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
