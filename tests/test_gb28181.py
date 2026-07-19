import pytest

from src.ingestion.gb28181 import GB28181Manager, GB28181StreamReader


class MockZLMClient:
    def __init__(self) -> None:
        self.proxies: list[dict] = []

    async def add_stream_proxy(self, app: str, stream: str, url: str) -> dict:
        self.proxies.append({"app": app, "stream": stream, "url": url})
        return {"code": 0, "data": {"key": "test_key"}}

    async def close_stream_proxy(self, app: str, stream: str) -> dict:
        self.proxies = [p for p in self.proxies if not (p["app"] == app and p["stream"] == stream)]
        return {"code": 0}

    async def get_media_list(self, app: str, stream: str) -> list:
        return [{"app": app, "stream": stream}]

    async def close(self) -> None:
        pass


@pytest.mark.asyncio
async def test_sip_register_device() -> None:
    mgr = GB28181Manager(MockZLMClient())
    device = await mgr.sip_register("34020000001320000001", "测试摄像头", "192.168.1.100")
    assert device.device_id == "34020000001320000001"
    assert device.name == "测试摄像头"
    assert device.registered_at != ""


@pytest.mark.asyncio
async def test_query_catalog() -> None:
    mgr = GB28181Manager(MockZLMClient())
    await mgr.sip_register("34020000001320000001", "测试摄像头")
    channels = await mgr.query_catalog("34020000001320000001")
    assert len(channels) == 2
    assert channels[0]["channel_id"].endswith("01")
    assert channels[1]["channel_id"].endswith("02")


@pytest.mark.asyncio
async def test_invite_stream_unknown_device_raises() -> None:
    mgr = GB28181Manager(MockZLMClient())
    with pytest.raises(KeyError):
        await mgr.invite_stream("nonexistent", "ch01")


@pytest.mark.asyncio
async def test_invite_stream_returns_rtsp_url() -> None:
    mgr = GB28181Manager(MockZLMClient())
    await mgr.sip_register("34020000001320000001", "测试摄像头")
    url = await mgr.invite_stream("34020000001320000001", "3402000000132000000101")
    assert url.startswith("rtsp://")
    assert "3402000000132000000101" in url


@pytest.mark.asyncio
async def test_bye_stream() -> None:
    mgr = GB28181Manager(MockZLMClient())
    await mgr.sip_register("34020000001320000001", "测试摄像头")
    await mgr.bye_stream("34020000001320000001", "ch01")
    device = await mgr.get_device("34020000001320000001")
    assert device is not None
    assert device.status == "offline"


@pytest.mark.asyncio
async def test_list_devices() -> None:
    mgr = GB28181Manager(MockZLMClient())
    await mgr.sip_register("dev01", "Device 1")
    await mgr.sip_register("dev02", "Device 2")
    devices = await mgr.list_devices()
    assert len(devices) == 2


@pytest.mark.asyncio
async def test_gb28181_stream_reader_init() -> None:
    reader = GB28181StreamReader("cam-gb01", "rtsp://localhost/gb28181/test", fps=2.0)
    assert reader.camera_id == "cam-gb01"
    assert reader.target_fps == 2.0
    assert reader.is_connected() is False


@pytest.mark.asyncio
async def test_gb28181_stream_reader_disconnect_idle() -> None:
    reader = GB28181StreamReader("cam-gb01", "rtsp://localhost/gb28181/test", fps=1.0)
    assert reader.is_connected() is False
    await reader.disconnect()
    assert reader.is_connected() is False
