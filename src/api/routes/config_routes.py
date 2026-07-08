from fastapi import APIRouter

from src.core.config_manager import config_manager

router = APIRouter(prefix="/v1/config", tags=["config"])


@router.get("/")
async def get_config(section: str | None = None) -> dict:
    if section:
        return config_manager.get_section(section)
    return config_manager.all()


@router.post("/reload")
async def reload_config() -> dict:
    changed = config_manager.check_reload()
    return {"ok": True, "reloaded": changed}
