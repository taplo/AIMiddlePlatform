from fastapi import APIRouter

from src.routing.scene_router import SceneRouter
from src.routing.matchers import camera_id_matcher, scene_type_matcher

router = APIRouter(prefix="/api/v1/routing", tags=["routing"])

_router: SceneRouter | None = None


def init_router(scene_router: SceneRouter) -> None:
    global _router
    _router = scene_router


@router.post("/routes")
async def add_route(body: dict) -> dict:
    if _router is None:
        return {"error": "Router not initialized"}
    _router.register_route(body["scene_id"], body["pipeline"])
    return {"ok": True, "scene_id": body["scene_id"], "pipeline": body["pipeline"]}


@router.delete("/routes/{scene_id}")
async def remove_route(scene_id: str) -> dict:
    if _router is None:
        return {"error": "Router not initialized"}
    _router.unregister_route(scene_id)
    return {"ok": True, "scene_id": scene_id}


@router.post("/matchers/camera_id")
async def add_camera_matcher(body: dict) -> dict:
    if _router is None:
        return {"error": "Router not initialized"}
    camera_map = body.get("mapping", {})
    _router.add_matcher(camera_id_matcher(camera_map))
    return {"ok": True, "entries": len(camera_map)}


@router.post("/matchers/scene_type")
async def add_scene_type_matcher(body: dict) -> dict:
    if _router is None:
        return {"error": "Router not initialized"}
    scene_map = body.get("mapping", {})
    _router.add_matcher(scene_type_matcher(scene_map))
    return {"ok": True, "entries": len(scene_map)}


@router.post("/reload")
async def reload_routes() -> dict:
    if _router is None:
        return {"error": "Router not initialized"}
    changed = _router.check_reload()
    return {"ok": True, "reloaded": changed}
