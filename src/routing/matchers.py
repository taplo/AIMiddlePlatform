from src.routing.scene_router import SceneMatcher


def camera_id_matcher(routes: dict[str, str]) -> SceneMatcher:
    def matcher(context: dict) -> str | None:
        camera_id = context.get("camera_id")
        if camera_id and camera_id in routes:
            return routes[camera_id]
        return None
    return matcher


def scene_type_matcher(scene_map: dict[str, str]) -> SceneMatcher:
    def matcher(context: dict) -> str | None:
        scene_type = context.get("scene_type")
        if scene_type and scene_type in scene_map:
            return scene_map[scene_type]
        return None
    return matcher
