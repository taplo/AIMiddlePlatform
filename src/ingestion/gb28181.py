import asyncio
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx

from src.ingestion.stream import Frame, StreamReader
from src.ingestion.zlmediakit import ZLMediaKitClient

logger = logging.getLogger(__name__)


@dataclass
class GB28181Device:
    device_id: str
    name: str
    manufacturer: str = "unknown"
    model: str = "unknown"
    status: str = "offline"
    stream_app: str = "gb28181"
    stream_id: str = ""
    channels: list[dict] | None = None
    registered_at: str = ""


@dataclass
class GB28181Channel:
    channel_id: str
    name: str
    parent_id: str
    status: str = "off"
    stream_url: str = ""


class GB28181Manager:
    def __init__(self, zlm_client: ZLMediaKitClient) -> None:
        self.zlm = zlm_client
        self._devices: dict[str, GB28181Device] = {}

    async def sip_register(self, device_id: str, name: str, ip: str = "", port: int = 5060) -> GB28181Device:
        device = GB28181Device(
            device_id=device_id,
            name=name,
            stream_id=device_id,
            registered_at=datetime.now().isoformat(),
        )
        self._devices[device_id] = device
        logger.info("GB28181 SIP device registered: %s (%s) at %s:%d", device_id, name, ip, port)
        return device

    async def query_catalog(self, device_id: str) -> list[dict]:
        device = self._devices.get(device_id)
        if device is None:
            raise KeyError(f"Device not registered: {device_id}")
        channels = [
            {"channel_id": f"{device_id}01", "name": f"{device.name}-主通道", "status": "ON"},
            {"channel_id": f"{device_id}02", "name": f"{device.name}-子通道", "status": "OFF"},
        ]
        device.channels = channels
        logger.info("Catalog queried for %s: %d channels", device_id, len(channels))
        return channels

    async def invite_stream(self, device_id: str, channel_id: str) -> str:
        device = self._devices.get(device_id)
        if device is None:
            raise KeyError(f"Device not registered: {device_id}")
        rtsp_url = f"rtsp://localhost/{device.stream_app}/{channel_id}"
        await self.zlm.add_stream_proxy(
            app=device.stream_app,
            stream=channel_id,
            url=f"rtsp://{device_id}:8554/{channel_id}",
        )
        device.status = "streaming"
        logger.info("GB28181 stream invited: %s/%s -> %s", device_id, channel_id, rtsp_url)
        return rtsp_url

    async def bye_stream(self, device_id: str, channel_id: str) -> None:
        device = self._devices.get(device_id)
        if device is None:
            return
        await self.zlm.close_stream_proxy(
            app=device.stream_app,
            stream=channel_id,
        )
        device.status = "offline"

    async def list_devices(self) -> list[GB28181Device]:
        return list(self._devices.values())

    async def get_device(self, device_id: str) -> GB28181Device | None:
        return self._devices.get(device_id)


class GB28181StreamReader(StreamReader):
    def __init__(self, camera_id: str, rtsp_url: str, fps: float = 1.0) -> None:
        self.camera_id = camera_id
        self.rtsp_url = rtsp_url
        self.target_fps = fps
        import cv2
        self._cap: cv2.VideoCapture | None = None
        self._frame_count = 0
        self._running = False

    async def connect(self) -> None:
        import cv2
        loop = asyncio.get_event_loop()
        self._cap = await loop.run_in_executor(
            None, lambda: cv2.VideoCapture(self.rtsp_url)
        )
        if self._cap is not None and not self._cap.isOpened():
            raise ConnectionError(f"Failed to open GB28181 stream: {self.rtsp_url}")
        self._running = True
        logger.info("GB28181 connected: %s (%s)", self.camera_id, self.rtsp_url)

    async def read_frames(self) -> AsyncIterator[Frame]:
        if self._cap is None:
            return
        loop = asyncio.get_event_loop()
        interval = 1.0 / self.target_fps if self.target_fps > 0 else 0
        while self._running:
            ret, frame_data = await loop.run_in_executor(None, self._cap.read)
            if not ret:
                break
            self._frame_count += 1
            yield Frame(
                data=frame_data,
                camera_id=self.camera_id,
                timestamp=asyncio.get_event_loop().time(),
                frame_number=self._frame_count,
            )
            if interval > 0:
                await asyncio.sleep(interval)

    async def disconnect(self) -> None:
        self._running = False
        if self._cap is not None:
            self._cap.release()
            self._cap = None

    def is_connected(self) -> bool:
        return self._cap is not None and self._cap.isOpened()
