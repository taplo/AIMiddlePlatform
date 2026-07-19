import asyncio
import logging
import time

logger = logging.getLogger(__name__)


class LLMHealthChecker:
    def __init__(self, check_interval: float = 30.0, timeout: float = 5.0):
        self._available = True
        self._check_interval = check_interval
        self._timeout = timeout
        self._last_check = 0.0
        self._task: asyncio.Task | None = None

    @property
    def available(self) -> bool:
        return self._available

    async def check(self, client) -> bool:
        start = time.monotonic()
        try:
            async with asyncio.timeout(self._timeout):
                await client.ping()
            self._available = True
            logger.debug("LLM health check passed (%.0fms)", (time.monotonic() - start) * 1000)
        except Exception as e:
            self._available = False
            logger.warning("LLM health check failed: %s", e)
        return self._available

    async def start_periodic_check(self, client) -> None:
        async def _loop():
            while True:
                await self.check(client)
                await asyncio.sleep(self._check_interval)
        self._task = asyncio.create_task(_loop(), name="llm-health-check")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass


_health_checker = LLMHealthChecker()


def get_health_checker() -> LLMHealthChecker:
    return _health_checker
