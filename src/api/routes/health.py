from fastapi import APIRouter

router = APIRouter(prefix="/api/v1/health", tags=["health"])


@router.get("")
async def health() -> dict:
    return {"status": "ok", "service": "aimiddleplatform", "version": "0.1.0"}
