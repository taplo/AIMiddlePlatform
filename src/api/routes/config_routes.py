from fastapi import APIRouter

from src.core.config import settings

router = APIRouter(prefix="/api/v1/config", tags=["config"])


@router.get("")
async def get_config(section: str | None = None) -> dict:
    if section:
        val = settings.get(section)
        return {section: val} if val else {}
    from src.core.config import _ENV_KEY_MAP
    sections = {}
    for key in _ENV_KEY_MAP:
        top = key.split(".")[0]
        if top not in sections:
            val = settings.get(top)
            if val is not None:
                sections[top] = val
    return sections
