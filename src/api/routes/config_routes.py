from fastapi import APIRouter

from src.core.config import settings

router = APIRouter(prefix="/api/v1/config", tags=["config"])


@router.get("")
async def get_config(section: str | None = None) -> dict:
    if section:
        val = settings.get(section)
        return {section: val} if val else {}
    return {}
