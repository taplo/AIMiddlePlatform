import json
from src.core.redis_client import get_redis


async def publish(channel: str, data: dict) -> None:
    redis_conn = await get_redis()
    await redis_conn.publish(channel, json.dumps(data, default=str))
