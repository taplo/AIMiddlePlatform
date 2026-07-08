from fastapi.testclient import TestClient

from src.api.app import app
from src.models.registry import ModelRegistry, ModelSpec
from src.api.routes import models as models_route

client = TestClient(app)


def test_list_config() -> None:
    resp = client.get("/v1/config/")
    assert resp.status_code == 200
    data = resp.json()
    assert "app" in data


def test_config_section() -> None:
    resp = client.get("/v1/config/?section=ingestion")
    assert resp.status_code == 200
    assert "max_streams" in resp.json()


def test_config_reload() -> None:
    resp = client.post("/v1/config/reload")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


def test_list_models_empty() -> None:
    resp = client.get("/v1/models/")
    assert resp.status_code == 200
    assert resp.json() == []


def test_register_and_list_models() -> None:
    registry = ModelRegistry()
    registry.register(ModelSpec(model_id="test_m", name="Test", version="1.0.0"))
    models_route.init_registry(registry)

    resp = client.get("/v1/models/")
    assert resp.status_code == 200
    models = resp.json()
    assert len(models) == 1
    assert models[0]["model_id"] == "test_m"


def test_get_specific_model() -> None:
    registry = ModelRegistry()
    registry.register(ModelSpec(model_id="specific", name="Specific", version="2.0.0"))
    models_route.init_registry(registry)

    resp = client.get("/v1/models/specific")
    assert resp.status_code == 200
    assert resp.json()["version"] == "2.0.0"


def test_get_nonexistent_model() -> None:
    registry = ModelRegistry()
    models_route.init_registry(registry)

    resp = client.get("/v1/models/nonexistent")
    assert resp.status_code == 404


def test_active_models() -> None:
    registry = ModelRegistry()
    from src.models.registry import ModelStatus
    registry.register(ModelSpec(model_id="m1", name="M1", version="1.0.0"))
    registry.register(ModelSpec(model_id="m2", name="M2", version="1.0.0",
                                status=ModelStatus.OFFLINE))
    models_route.init_registry(registry)

    resp = client.get("/v1/models/active")
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_routing_add_route() -> None:
    from src.routing.scene_router import SceneRouter
    from src.api.routes.routing import init_router

    router = SceneRouter()
    init_router(router)

    resp = client.post("/v1/routing/routes", json={"scene_id": "test", "pipeline": "p1"})
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


def test_routing_delete_route() -> None:
    from src.routing.scene_router import SceneRouter
    from src.api.routes.routing import init_router

    router = SceneRouter()
    router.register_route("del_me", "p1")
    init_router(router)

    resp = client.delete("/v1/routing/routes/del_me")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


def test_analyze_ping() -> None:
    resp = client.get("/v1/analyze/ping")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
