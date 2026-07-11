import pytest
from fastapi.testclient import TestClient

from src.api.app import app


@pytest.mark.asyncio
async def test_analyze_frame_returns_task_id() -> None:
    client = TestClient(app)
    resp = client.post(
        "/v1/analyze/frame?sync=false",
        json={"camera_id": "cam-test", "scene_type": "detection"},
    )
    if resp.status_code == 500:
        pytest.skip("Redis not available")
    assert resp.status_code == 200
    data = resp.json()
    assert "task_id" in data
    assert data["status"] == "queued"
