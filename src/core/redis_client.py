import asyncio
import logging

import redis.asyncio as aioredis

from src.core.config import settings

logger = logging.getLogger(__name__)

_redis: aioredis.Redis | None = None
_redis_unavailable: bool = False
_redis_loop_id: int | None = None
_RETRY_DELAYS = [0.5, 1.0, 2.0]


async def get_redis() -> aioredis.Redis | None:
    global _redis, _redis_unavailable, _redis_loop_id
    if _redis_unavailable:
        return None
    if _redis is not None:
        try:
            current_loop = asyncio.get_running_loop()
            if id(current_loop) != _redis_loop_id:
                await _redis.aclose()
                _redis = None
        except RuntimeError:
            _redis = None
    if _redis is not None:
        return _redis
    redis_url = settings.get("queue.redis_url", "redis://localhost:6379/0")
    last_error = None
    for attempt, delay in enumerate(_RETRY_DELAYS + [0]):
        try:
            r = await aioredis.from_url(redis_url, socket_connect_timeout=2)
            await r.ping()
            _redis = r
            _redis_loop_id = id(asyncio.get_running_loop())
            logger.info("shared Redis client connected to %s", redis_url)
            return _redis
        except Exception as e:
            last_error = e
            _redis = None
            _redis_loop_id = None
            if attempt < len(_RETRY_DELAYS):
                logger.warning("Redis connection attempt %d failed: %s, retrying in %.1fs", attempt + 1, e, delay)
                await asyncio.sleep(delay)
    logger.error("Redis connection failed after %d attempts: %s", len(_RETRY_DELAYS) + 1, last_error)
    _redis_unavailable = True
    return None


async def close_redis() -> None:
    global _redis, _redis_unavailable, _redis_loop_id
    if _redis is not None:
        await _redis.aclose()
        _redis = None
    _redis_unavailable = False
    _redis_loop_id = None


async def ping() -> bool:
    try:
        r = await get_redis()
        if r is None:
            return False
        return await r.ping()
    except Exception:
        return False
