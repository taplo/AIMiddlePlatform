import asyncio
import logging

from src.ingestion.frame_extractor import FPSConfig

logger = logging.getLogger(__name__)


class BackpressureController:
    def __init__(
        self,
        fps_config: FPSConfig,
        check_interval: float = 5.0,
        backlog_size_fn=None,
    ) -> None:
        self.fps_config = fps_config
        self.check_interval = check_interval
        self._backlog_size_fn = backlog_size_fn or (lambda: 0)
        self._running = False

    async def start(self) -> None:
        self._running = True
        while self._running:
            backlog = self._backlog_size_fn()
            if backlog > self.fps_config._backlog_threshold:
                self.fps_config.reduce_fps()
            elif backlog < self.fps_config._backlog_threshold // 2:
                self.fps_config.restore_fps()
            await asyncio.sleep(self.check_interval)

    def stop(self) -> None:
        self._running = False
