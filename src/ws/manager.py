import asyncio
import logging
from redis.asyncio import Redis
from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self, redis_url: str, ping_interval: int = 30):
        self._connections: list[WebSocket] = []
        self._redis_url = redis_url
        self._ping_interval = ping_interval
        self._redis: Redis | None = None
        self._subscriber_task: asyncio.Task | None = None

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._connections.append(ws)

    async def disconnect(self, ws: WebSocket) -> None:
        self._connections.remove(ws)

    async def start(self) -> None:
        self._redis = Redis.from_url(self._redis_url)
        self._subscriber_task = asyncio.create_task(self._subscriber_loop())

    async def stop(self) -> None:
        if self._subscriber_task:
            self._subscriber_task.cancel()
        if self._redis:
            await self._redis.close()

    async def _subscriber_loop(self) -> None:
        if not self._redis:
            return
        pubsub = self._redis.pubsub()
        await pubsub.subscribe("ws:analysis_result", "ws:alert", "ws:system_event")
        try:
            async for msg in pubsub.listen():
                if msg["type"] == "message":
                    data = msg["data"]
                    if isinstance(data, bytes):
                        data = data.decode("utf-8")
                    await self._broadcast(data)
        except asyncio.CancelledError:
            pass
        finally:
            await pubsub.unsubscribe()

    async def _broadcast(self, data: str) -> None:
        dead: list[WebSocket] = []
        for ws in self._connections:
            try:
                await ws.send_text(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            try:
                self._connections.remove(ws)
            except ValueError:
                pass
