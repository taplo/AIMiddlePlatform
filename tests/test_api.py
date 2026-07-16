import pytest
from httpx import ASGITransport, AsyncClient
from starlette.testclient import TestClient

from src.api.app import app

_TEST_API_KEY = "sk-test-api-key-for-old-tests-abcdef1234"


@pytest.fixture(autouse=True)
def _setup_api_key():
    from src.core.security import get_api_key_store
    store = get_api_key_store()
    store.add_key("test", _TEST_API_KEY, rate_per_second=1000)
    yield


def _headers() -> dict:
    return {"X-API-Key": _TEST_API_KEY}


@pytest.mark.asyncio
async def test_health() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"


def test_register_stream() -> None:
    client = TestClient(app)
    resp = client.post(
        "/api/v1/analyze/stream",
        json={"stream_url": "rtsp://test/stream", "protocol": "rtsp"},
        headers=_headers(),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["stream_url"] == "rtsp://test/stream"
    assert data["protocol"] == "rtsp"
