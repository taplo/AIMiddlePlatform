import logging
from dataclasses import dataclass
from datetime import datetime

from src.ingestion.rtsp import RTSPStreamReader
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


class GB28181StreamReader(RTSPStreamReader):
    def __init__(self, camera_id: str, rtsp_url: str, fps: float = 1.0) -> None:
        super().__init__(camera_id, rtsp_url, fps)
        logger.info("GB28181 stream reader created: %s (%s)", camera_id, rtsp_url)
