import asyncio
import logging
from redis.asyncio import Redis
from redis import RedisError
from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self, redis_url: str, ping_interval: int = 30, max_connections: int = 10000):
        self._connections: list[WebSocket] = []
        self._redis_url = redis_url
        self._ping_interval = ping_interval
        self._max_connections = max_connections
        self._redis: Redis | None = None
        self._subscriber_task: asyncio.Task | None = None

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        if len(self._connections) >= self._max_connections:
            await ws.close(code=1008)
            return
        self._connections.append(ws)
        asyncio.create_task(self._heartbeat_loop(ws))

    async def _heartbeat_loop(self, ws: WebSocket) -> None:
        try:
            while True:
                await asyncio.sleep(self._ping_interval)
                try:
                    import json
                    await ws.send_text(json.dumps({"type": "ping"}))
                except Exception:
                    await self.disconnect(ws)
                    return
        except asyncio.CancelledError:
            pass

    async def disconnect(self, ws: WebSocket) -> None:
        try:
            self._connections.remove(ws)
        except ValueError:
            pass

    async def start(self) -> None:
        self._redis = Redis.from_url(self._redis_url)
        self._subscriber_task = asyncio.create_task(self._subscriber_loop())

    async def stop(self) -> None:
        if self._subscriber_task:
            self._subscriber_task.cancel()
        if self._redis:
            await self._redis.close()

    async def _subscriber_loop(self) -> None:
        import asyncio
        retry_delay = 1
        max_delay = 60
        while True:
            try:
                pubsub = self._redis.pubsub()
                await pubsub.subscribe("ws:analysis_result", "ws:alert", "ws:system_event")
                retry_delay = 1
                try:
                    async for msg in pubsub.listen():
                        if msg["type"] == "message":
                            data = msg["data"]
                            if isinstance(data, bytes):
                                data = data.decode("utf-8")
                            await self._broadcast(data)
                except asyncio.CancelledError:
                    break
                finally:
                    await pubsub.unsubscribe()
            except (RedisError, ConnectionError, OSError) as e:
                logger.warning("Redis subscriber disconnected: %s, retrying in %ds", e, retry_delay)
                if retry_delay < max_delay:
                    retry_delay = min(retry_delay * 2, max_delay)
                await asyncio.sleep(retry_delay)

    async def _broadcast(self, data: str) -> None:
        conns = self._connections.copy()
        if not conns:
            return

        async def _send(ws: WebSocket) -> bool:
            try:
                await ws.send_text(data)
                return True
            except Exception:
                return False

        results = await asyncio.gather(*[_send(ws) for ws in conns])
        for ws, ok in zip(conns, results):
            if not ok:
                try:
                    self._connections.remove(ws)
                except ValueError:
                    pass
