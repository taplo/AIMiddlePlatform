import asyncio
import logging
from collections.abc import AsyncIterator

from src.ingestion.stream import Frame, StreamReader
from src.ingestion.rtsp import RTSPStreamReader

logger = logging.getLogger(__name__)


class StreamManager:
    def __init__(self, reconnect_interval: int = 5) -> None:
        self._readers: dict[str, StreamReader] = {}
        self._reconnect_interval = reconnect_interval

    async def add_stream(
        self, camera_id: str, stream_url: str, protocol: str = "rtsp", fps: float = 1.0
    ) -> None:
        if protocol == "rtsp":
            reader: StreamReader = RTSPStreamReader(camera_id, stream_url, fps)
        else:
            raise ValueError(f"Unsupported protocol: {protocol}")

        await reader.connect()
        self._readers[camera_id] = reader
        logger.info("Stream added: %s (%s)", camera_id, stream_url)

    async def remove_stream(self, camera_id: str) -> None:
        reader = self._readers.pop(camera_id, None)
        if reader is not None:
            await reader.disconnect()

    async def read_frames(self, camera_id: str) -> AsyncIterator[Frame]:
        reader = self._readers.get(camera_id)
        if reader is None:
            raise KeyError(f"Stream not found: {camera_id}")

        async for frame in reader.read_frames():
            yield frame

    async def ensure_connected(self, camera_id: str) -> None:
        reader = self._readers.get(camera_id)
        if reader is not None and not reader.is_connected():
            logger.warning("Reconnecting %s...", camera_id)
            await reader.connect()

    async def monitor(self) -> None:
        while True:
            for camera_id in list(self._readers.keys()):
                await self.ensure_connected(camera_id)
            await asyncio.sleep(self._reconnect_interval)

    def list_streams(self) -> list[str]:
        return list(self._readers.keys())

    async def shutdown(self) -> None:
        for camera_id in list(self._readers.keys()):
            await self.remove_stream(camera_id)
