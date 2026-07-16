import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.api.app import app
from src.api import deps as api_deps
from src.api.routes import tasks as tasks_route
from src.api.routes import alerts as alerts_route
from src.core.database import Task, Alert, init_db

pytestmark = pytest.mark.usefixtures('_setup_db')
client = TestClient(app)
_TEST_API_KEY = "sk-test-api-key-for-tests-12345678"


@pytest.fixture(autouse=True)
def _setup_api_key():
    from src.core.security import get_api_key_store
    store = get_api_key_store()
    store.add_key("test", _TEST_API_KEY, rate_per_second=1000)
    yield


def _headers() -> dict:
    return {"X-API-Key": _TEST_API_KEY}


@pytest.fixture
async def _setup_db():
    engine = await init_db("sqlite+aiosqlite://")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    prev = api_deps._session_factory
    api_deps.init_session_factory(factory)
    async with factory() as session:
        session.add_all([
            Task(id="t1", camera_id="cam-1", status="completed", path_taken="fast", latency_ms=50),
            Task(id="t2", camera_id="cam-1", status="completed", path_taken="agent", latency_ms=1200),
            Task(id="t3", camera_id="cam-2", status="rejected", path_taken="rejected", rejection_reason="quality_blurry"),
            Task(id="t4", camera_id="cam-2", status="skipped", path_taken="skipped", rejection_reason="sampling_duplicate"),
        ])
        session.add_all([
            Alert(task_id="t1", alert_type="person_detected", label="person", confidence=0.95, verified_by="model", status="confirmed"),
            Alert(task_id="t1", alert_type="vehicle_detected", label="car", confidence=0.88, verified_by="model", status="confirmed"),
            Alert(task_id="t3", alert_type="quality_rejected", label="quality_blurry", confidence=0.0, verified_by="model", status="pending"),
        ])
        await session.commit()
    yield
    api_deps.init_session_factory(prev)


def test_list_tasks_all() -> None:
    resp = client.get("/api/v1/tasks", headers=_headers())
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 4
    assert len(data["items"]) == 4
    assert data["page"] == 1
    assert data["page_size"] == 20


def test_list_tasks_filter_status() -> None:
    resp = client.get("/api/v1/tasks?status=completed", headers=_headers())
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert all(item["status"] == "completed" for item in data["items"])


def test_list_tasks_filter_camera() -> None:
    resp = client.get("/api/v1/tasks?camera_id=cam-2", headers=_headers())
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert all(item["camera_id"] == "cam-2" for item in data["items"])


def test_list_tasks_pagination() -> None:
    resp = client.get("/api/v1/tasks?page=1&page_size=2", headers=_headers())
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 4
    assert len(data["items"]) == 2


def test_get_task_result() -> None:
    resp = client.get("/api/v1/tasks/t1/results", headers=_headers())
    assert resp.status_code == 200
    data = resp.json()
    assert data["task_id"] == "t1"
    assert data["status"] == "completed"
    assert data["camera_id"] == "cam-1"


def test_get_task_result_rejected() -> None:
    resp = client.get("/api/v1/tasks/t3/results", headers=_headers())
    assert resp.status_code == 200
    data = resp.json()
    assert data["rejection_reason"] == "quality_blurry"
    assert data["status"] == "rejected"


def test_get_task_result_not_found() -> None:
    resp = client.get("/api/v1/tasks/nonexistent/results", headers=_headers())
    assert resp.status_code == 404


def test_list_alerts_all() -> None:
    resp = client.get("/api/v1/alerts", headers=_headers())
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 3
    assert len(data["items"]) == 3


def test_list_alerts_filter_status() -> None:
    resp = client.get("/api/v1/alerts?status=pending", headers=_headers())
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1


def test_list_alerts_filter_type() -> None:
    resp = client.get("/api/v1/alerts?alert_type=person_detected", headers=_headers())
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1


def test_list_alerts_filter_task_id() -> None:
    resp = client.get("/api/v1/alerts?task_id=t3", headers=_headers())
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1


def test_get_alert_by_id() -> None:
    resp = client.get("/api/v1/alerts/1", headers=_headers())
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == 1
    assert "task_id" in data


def test_get_alert_not_found() -> None:
    resp = client.get("/api/v1/alerts/999", headers=_headers())
    assert resp.status_code == 404
