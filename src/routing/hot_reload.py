import asyncio
import logging

from src.routing.scene_router import SceneRouter

logger = logging.getLogger(__name__)


class HotReloadWatcher:
    def __init__(self, router: SceneRouter, interval: float = 10.0) -> None:
        self.router = router
        self.interval = interval
        self._running = False

    async def start(self) -> None:
        self._running = True
        while self._running:
            if self.router.check_reload():
                logger.info("Routes hot-reloaded")
            await asyncio.sleep(self.interval)

    def stop(self) -> None:
        self._running = False
