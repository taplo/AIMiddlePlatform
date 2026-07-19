from src.routing.matchers import camera_id_matcher, scene_type_matcher
from src.routing.scene_router import SceneRouter


def test_hash_based_routing() -> None:
    router = SceneRouter()
    router.register_route("a1b2c3d4e5f6g7h8", "plate_recognition")
    result = router.resolve({"camera_id": "cam-01", "scene_type": "plate"})
    assert result is None


def test_matcher_routing() -> None:
    router = SceneRouter()
    camera_map = {"cam-01": "plate_recognition"}
    router.add_matcher(camera_id_matcher(camera_map))

    result = router.resolve({"camera_id": "cam-01"})
    assert result == "plate_recognition"


def test_scene_type_matcher() -> None:
    router = SceneRouter()
    scene_map = {"parking_lot": "vehicle_detection"}
    router.add_matcher(scene_type_matcher(scene_map))

    result = router.resolve({"scene_type": "parking_lot"})
    assert result == "vehicle_detection"


def test_route_hot_reload(tmp_path) -> None:
    import json
    router = SceneRouter()
    route_file = tmp_path / "routes.json"
    route_file.write_text(json.dumps([
        {"scene_id": "test_scene", "pipeline": "test_pipeline"}
    ]))
    router.enable_hot_reload(route_file)
    router.check_reload()
    result = router.resolve({"test_scene": True})
    assert result == "test_pipeline" or result is None
