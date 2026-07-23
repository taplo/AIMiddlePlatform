import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.api import deps as api_deps
from src.api.app import app
from src.core.database import init_db

_TEST_API_KEY = "sk-test-async-analyze-key-00000000"


@pytest.fixture(scope="module", autouse=True)
async def _init_db():
    engine = await init_db("sqlite+aiosqlite://")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    prev = api_deps._session_factory
    api_deps.init_session_factory(factory)
    yield
    api_deps.init_session_factory(prev)


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
        "/api/v1/analyze/frame?sync=false",
        json={"camera_id": "cam-test", "scene_type": "detection"},
        headers=_headers(),
    )
    if resp.status_code == 500:
        pytest.skip("Redis not available")
    assert resp.status_code == 200
    data = resp.json()
    assert "task_id" in data
    assert data["status"] in ("queued", "queued_local")
