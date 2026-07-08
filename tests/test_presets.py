from src.models.registry import ModelRegistry
from src.models.presets import register_default_models


def test_default_models_registered() -> None:
    registry = ModelRegistry()
    register_default_models(registry)
    models = registry.list_models()
    model_ids = {m.model_id for m in models}
    expected = {"object_detection", "face_recognition", "license_plate",
                "vehicle_detection", "ocr", "person_reid"}
    assert model_ids == expected


def test_all_default_models_online() -> None:
    registry = ModelRegistry()
    register_default_models(registry)
    online = registry.get_active_models()
    assert len(online) == 6
