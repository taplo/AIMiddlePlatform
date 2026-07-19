import logging
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

from src.ingestion.stream import Frame

logger = logging.getLogger(__name__)


@dataclass
class FPSConfig:
    target_fps: float = 1.0
    min_fps: float = 0.1
    max_fps: float = 30.0
    dynamic_enabled: bool = True
    _backlog_threshold: int = 100
    _current_fps: float = field(default=1.0, init=False)

    def __post_init__(self) -> None:
        self._current_fps = self.target_fps

    def reduce_fps(self) -> None:
        if self.dynamic_enabled and self._current_fps > self.min_fps:
            self._current_fps = max(self._current_fps / 2, self.min_fps)
            logger.info("FPS reduced to %.2f", self._current_fps)

    def restore_fps(self) -> None:
        if self.dynamic_enabled:
            self._current_fps = min(self._current_fps * 2, self.target_fps)
            logger.info("FPS restored to %.2f", self._current_fps)

    @property
    def current_fps(self) -> float:
        return self._current_fps if self.dynamic_enabled else self.target_fps


class FrameExtractor:
    def __init__(self, fps_config: FPSConfig | None = None) -> None:
        self.fps_config = fps_config or FPSConfig()

    async def extract(
        self, frame_stream: AsyncIterator[Frame]
    ) -> AsyncIterator[Frame]:
        interval = 1.0 / self.fps_config.current_fps
        last_yield = 0.0

        async for frame in frame_stream:
            now = time.monotonic()
            if now - last_yield >= interval:
                last_yield = now
                yield frame
