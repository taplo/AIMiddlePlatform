import time
import logging

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_db
from src.core.redis_client import get_redis

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/health", tags=["health"])

_start_time = time.time()


def _uptime() -> float:
    return time.time() - _start_time


@router.get("")
async def health(db: AsyncSession = Depends(get_db)) -> dict:
    checks = {}
    overall = "ok"

    # Database check
    try:
        before = time.monotonic()
        await db.execute(text("SELECT 1"))
        db_latency = (time.monotonic() - before) * 1000
        checks["database"] = {"status": "ok", "latency_ms": round(db_latency, 1)}
    except Exception as e:
        checks["database"] = {"status": "error", "message": str(e)}
        overall = "error"

    # Redis check
    try:
        before = time.monotonic()
        redis = await get_redis()
        if redis is None:
            raise RuntimeError("Redis client unavailable")
        await redis.ping()
        redis_latency = (time.monotonic() - before) * 1000
        checks["redis"] = {"status": "ok", "latency_ms": round(redis_latency, 1)}
    except Exception as e:
        checks["redis"] = {"status": "degraded" if overall != "error" else "error", "message": str(e)}
        if overall == "ok":
            overall = "degraded"

    # LLM health check
    try:
        from src.agent.health import get_health_checker
        checker = get_health_checker()
        checks["llm"] = {"status": "ok", "available": checker.available}
    except Exception:
        checks["llm"] = {"status": "degraded", "available": False}
        if overall == "ok":
            overall = "degraded"

    # Model registry check
    try:
        from src.models.registry import ModelRegistry
        registry = ModelRegistry()
        models = registry.list_models()
        checks["model_registry"] = {"status": "ok", "models_count": len(models)}
    except Exception:
        checks["model_registry"] = {"status": "degraded"}
        if overall == "ok":
            overall = "degraded"

    return {
        "status": overall,
        "service": "aimiddleplatform",
        "version": "0.1.0",
        "uptime_seconds": int(_uptime()),
        "checks": checks,
    }
