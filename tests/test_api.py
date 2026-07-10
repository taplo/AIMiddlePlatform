import pytest
from httpx import ASGITransport, AsyncClient
from starlette.testclient import TestClient

from src.api.app import app


@pytest.mark.asyncio
async def test_health() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"


def test_register_stream() -> None:
    client = TestClient(app)
    resp = client.post(
        "/v1/analyze/stream",
        json={"stream_url": "rtsp://test/stream", "protocol": "rtsp"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["stream_url"] == "rtsp://test/stream"
    assert data["protocol"] == "rtsp"
