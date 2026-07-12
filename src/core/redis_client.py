import logging

import redis.asyncio as aioredis

from src.core.config import settings

logger = logging.getLogger(__name__)

_redis: aioredis.Redis | None = None


async def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        redis_url = settings.get("queue.redis_url", "redis://localhost:6379/0")
        _redis = await aioredis.from_url(redis_url)
        logger.info("shared Redis client connected to %s", redis_url)
    return _redis


async def close_redis() -> None:
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None


async def ping() -> bool:
    try:
        r = await get_redis()
        return await r.ping()
    except Exception:
        return False
