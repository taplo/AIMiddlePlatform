import json
import logging

from src.core.redis_client import get_redis

logger = logging.getLogger(__name__)


async def publish(channel: str, data: dict) -> None:
    try:
        redis_conn = await get_redis()
        await redis_conn.publish(channel, json.dumps(data, default=str))
    except Exception:
        logger.warning("Redis unavailable, skipping WS publish to %s", channel)
