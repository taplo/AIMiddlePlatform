from src.models.registry import ModelRegistry, ModelSpec, ModelStatus


def test_register_and_get() -> None:
    registry = ModelRegistry()
    spec = ModelSpec(model_id="test_model", name="测试模型", version="1.0.0")
    registry.register(spec)
    retrieved = registry.get("test_model")
    assert retrieved is not None
    assert retrieved.model_id == "test_model"
    assert retrieved.version == "1.0.0"


def test_get_versioned() -> None:
    registry = ModelRegistry()
    registry.register(ModelSpec(model_id="m1", name="M1", version="1.0.0"))
    registry.register(ModelSpec(model_id="m1", name="M1", version="2.0.0"))
    v1 = registry.get("m1", "1.0.0")
    assert v1 is not None and v1.version == "1.0.0"
    latest = registry.get("m1")
    assert latest is not None and latest.version == "2.0.0"


def test_list_models() -> None:
    registry = ModelRegistry()
    registry.register(ModelSpec(model_id="a", name="A", version="1.0.0"))
    registry.register(ModelSpec(model_id="b", name="B", version="1.0.0"))
    assert len(registry.list_models()) == 2


def test_status_filter() -> None:
    registry = ModelRegistry()
    registry.register(ModelSpec(model_id="online_m", name="On", version="1.0.0"))
    offline = ModelSpec(model_id="offline_m", name="Off", version="1.0.0",
                        status=ModelStatus.OFFLINE)
    registry.register(offline)
    online = registry.list_models(status=ModelStatus.ONLINE)
    assert len(online) == 1
    assert online[0].model_id == "online_m"


def test_set_status() -> None:
    registry = ModelRegistry()
    registry.register(ModelSpec(model_id="m", name="M", version="1.0.0"))
    registry.set_status("m", "1.0.0", ModelStatus.DEPRECATED)
    assert registry.get("m", "1.0.0") is not None
    assert registry.get("m", "1.0.0").status == ModelStatus.DEPRECATED


def test_get_active_models() -> None:
    registry = ModelRegistry()
    registry.register(ModelSpec(model_id="active", name="A", version="1.0.0"))
    registry.register(ModelSpec(model_id="inactive", name="B", version="1.0.0",
                                status=ModelStatus.OFFLINE))
    assert len(registry.get_active_models()) == 1


def test_list_empty() -> None:
    registry = ModelRegistry()
    assert registry.list_models() == []


def test_model_missing() -> None:
    registry = ModelRegistry()
    assert registry.get("nonexistent") is None
