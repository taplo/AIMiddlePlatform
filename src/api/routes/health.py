import asyncio
import logging
import time

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/health", tags=["health"])

_start = time.monotonic()

_HEALTH_TIMEOUT = 3.0


@router.get("")
async def health(db: AsyncSession = Depends(get_db)) -> dict:
    checks = {}
    overall = "ok"

    # Database check
    try:
        before = time.monotonic()
        await asyncio.wait_for(db.execute(text("SELECT 1")), timeout=_HEALTH_TIMEOUT)
        db_latency = (time.monotonic() - before) * 1000
        checks["database"] = {"status": "ok", "latency_ms": round(db_latency, 1)}
    except Exception as e:
        checks["database"] = {"status": "error", "message": str(e)}
        overall = "error"

    # Redis check
    try:
        from src.core.redis_client import get_redis
        before = time.monotonic()
        redis = await get_redis()
        if redis is None:
            raise RuntimeError("Redis client unavailable")
        await asyncio.wait_for(redis.ping(), timeout=_HEALTH_TIMEOUT)
        redis_latency = (time.monotonic() - before) * 1000
        checks["redis"] = {"status": "ok", "latency_ms": round(redis_latency, 1)}
    except Exception as e:
        checks["redis"] = {"status": "degraded", "message": str(e)}
        if overall == "ok":
            overall = "degraded"

    # LLM health check
    try:
        from src.agent.health import get_health_checker
        checker = get_health_checker()
        checks["llm"] = {"status": "ok", "available": checker.available}
    except Exception:
        logger.exception("LLM health check failed")
        checks["llm"] = {"status": "degraded", "available": False}
        if overall == "ok":
            overall = "degraded"

    # Model registry check
    try:
        import src.api.routes.models as models_route
        models = models_route._registry
        count = len(models.list_models()) if models else 0
        checks["model_registry"] = {"status": "ok", "models_count": count}
    except Exception:
        logger.exception("Model registry health check failed")
        checks["model_registry"] = {"status": "degraded"}
        if overall == "ok":
            overall = "degraded"

    return {
        "status": overall,
        "service": "aimiddleplatform",
        "version": "0.2.0",
        "uptime_seconds": int(time.monotonic() - _start),
        "checks": checks,
    }
