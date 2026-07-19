import asyncio
import logging
import time
from collections.abc import AsyncIterator

import cv2

from src.ingestion.stream import Frame, StreamReader

logger = logging.getLogger(__name__)


class RTSPStreamReader(StreamReader):
    def __init__(self, camera_id: str, stream_url: str, fps: float = 1.0) -> None:
        self.camera_id = camera_id
        self.stream_url = stream_url
        self.target_fps = fps
        self._cap: cv2.VideoCapture | None = None
        self._frame_count = 0
        self._running = False

    async def connect(self) -> None:
        loop = asyncio.get_event_loop()
        cap = await loop.run_in_executor(
            None, lambda: cv2.VideoCapture(self.stream_url)
        )
        if not cap.isOpened():
            raise ConnectionError(f"Failed to open RTSP stream: {self.stream_url}")
        self._cap = cap
        self._running = True
        logger.info("Connected to %s (%s)", self.camera_id, self.stream_url)

    async def read_frames(self) -> AsyncIterator[Frame]:
        if self._cap is None:
            return
        loop = asyncio.get_event_loop()

        while self._running:
            ret, frame_data = await loop.run_in_executor(None, self._cap.read)
            if not ret:
                logger.warning("Frame read failed for %s", self.camera_id)
                break

            self._frame_count += 1
            yield Frame(
                data=frame_data,
                camera_id=self.camera_id,
                timestamp=time.monotonic(),
                frame_number=self._frame_count,
            )

    async def disconnect(self) -> None:
        self._running = False
        if self._cap is not None:
            self._cap.release()
            self._cap = None
        logger.info("Disconnected %s", self.camera_id)

    def is_connected(self) -> bool:
        return self._cap is not None and self._cap.isOpened()
