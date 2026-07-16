import logging

from fastapi import APIRouter, HTTPException

from src.core.security import get_api_key_store, get_rate_limiter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/admin/api-keys", tags=["admin"])


@router.get("")
async def list_api_keys() -> dict:
    store = get_api_key_store()
    return {"keys": store.list_keys(), "total": store.count()}


@router.post("")
async def create_api_key(body: dict) -> dict:
    name = body.get("name", "")
    key = body.get("key", "")
    rate = body.get("rate_per_second", 10)
    if not name or not key:
        raise HTTPException(400, "name and key are required")
    store = get_api_key_store()
    try:
        store.add_key(name, key, rate)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"name": name, "key_prefix": key[:8] + "...", "rate_per_second": rate}


@router.delete("/{key}")
async def delete_api_key(key: str) -> dict:
    store = get_api_key_store()
    await get_rate_limiter().reset(key)
    if store.remove_key(key):
        return {"status": "deleted"}
    raise HTTPException(404, "API key not found")
