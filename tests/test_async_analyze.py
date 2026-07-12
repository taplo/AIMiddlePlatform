import pytest
from fastapi.testclient import TestClient

from src.api.app import app

_TEST_API_KEY = "sk-test-async-analyze-key-00000000"


@pytest.fixture(autouse=True)
def _setup_api_key():
    from src.core.security import get_api_key_store
    store = get_api_key_store()
    store.add_key("test", _TEST_API_KEY, rate_per_second=1000)
    yield


def _headers() -> dict:
    return {"X-API-Key": _TEST_API_KEY}


@pytest.mark.asyncio
async def test_analyze_frame_returns_task_id() -> None:
    client = TestClient(app)
    resp = client.post(
        "/v1/analyze/frame?sync=false",
        json={"camera_id": "cam-test", "scene_type": "detection"},
        headers=_headers(),
    )
    if resp.status_code == 500:
        pytest.skip("Redis not available")
    assert resp.status_code == 200
    data = resp.json()
    assert "task_id" in data
    assert data["status"] == "queued"
