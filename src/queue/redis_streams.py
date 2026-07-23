import asyncio
import logging
from collections.abc import AsyncIterator

import redis.asyncio as aioredis
from redis.exceptions import ConnectionError as RedisConnectionError

from src.core.config import settings
from src.core.redis_client import get_redis
from src.queue.interface import FrameQueue

logger = logging.getLogger(__name__)


class RedisStreamQueue(FrameQueue):
    def __init__(self) -> None:
        self._consumer_group = settings.get("queue.consumer_group", "ingestion_workers")
        self._consumer_id = f"worker-{id(self)}"

    async def _ensure_redis(self) -> aioredis.Redis:
        return await get_redis()

    async def push(self, camera_id: str, data: bytes) -> None:
        r = await self._ensure_redis()
        if r is None:
            raise RedisConnectionError("Redis unavailable")
        stream_key = f"frames:{camera_id}"
        await r.xadd(stream_key, {"data": data}, maxlen=10000)

    async def consume(self, camera_id: str) -> AsyncIterator[bytes]:
        r = await self._ensure_redis()
        stream_key = f"frames:{camera_id}"

        try:
            await r.xgroup_create(stream_key, self._consumer_group, id="0", mkstream=True)
        except aioredis.ResponseError:
            pass

        while True:
            results = await r.xreadgroup(
                self._consumer_group,
                self._consumer_id,
                {stream_key: ">"},
                count=1,
                block=1000,
            )
            if results:
                for _, messages in results:
                    for msg_id, msg_data in messages:
                        yield msg_data.get(b"data", b"")
                        await r.xack(stream_key, self._consumer_group, msg_id)
            await asyncio.sleep(0)

    async def backlog_size(self, camera_id: str) -> int:
        r = await self._ensure_redis()
        stream_key = f"frames:{camera_id}"
        try:
            info = await r.xpending(stream_key, self._consumer_group)
            return info.get("pending", 0)
        except aioredis.ResponseError:
            return 0

    async def ack(self, camera_id: str, message_id: str) -> None:
        r = await self._ensure_redis()
        stream_key = f"frames:{camera_id}"
        await r.xack(stream_key, self._consumer_group, message_id)
