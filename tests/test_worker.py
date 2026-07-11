import json
import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.database import init_db, Task
from src.worker import Worker
from src.agent.client import QwenVLClient


@pytest.mark.asyncio
async def test_worker_processes_and_saves():
    db = await init_db("sqlite+aiosqlite:///:memory:")
    transport = httpx.MockTransport(lambda req: httpx.Response(200, json={
        "choices": [{"message": {
            "content": '{"scene_type": "unknown", "objects": [], "anomalies": [], "summary": "no fast path match"}',
            "role": "assistant",
        }}]
    }))
    worker = Worker(db)
    worker.orchestrator.agent.llm = QwenVLClient(http_client=httpx.AsyncClient(transport=transport))
    msg = {
        "task_id": "test-001",
        "camera_id": "cam-test",
        "frame": "",
        "scene_type": "unknown",
    }
    result = await worker.process_one(msg)
    assert "path" in result

    async with AsyncSession(db) as session:
        task = await session.get(Task, "test-001")
        assert task is not None
        assert task.status == "completed"
        assert task.camera_id == "cam-test"


@pytest.mark.asyncio
async def test_worker_falls_through_to_agent():
    """When FastPath returns None, Worker should fall through to Agent path."""
    db = await init_db("sqlite+aiosqlite:///:memory:")

    transport = httpx.MockTransport(lambda req: httpx.Response(200, json={
        "choices": [{"message": {
            "content": '{"scene_type": "unknown", "objects": [], "anomalies": [], "summary": "no fast path match"}',
            "role": "assistant",
        }}]
    }))
    worker = Worker(db)
    worker.orchestrator.agent.llm = QwenVLClient(http_client=httpx.AsyncClient(transport=transport))

    msg = {
        "task_id": "agent-test-001",
        "camera_id": "cam-unknown",
        "frame": "",
        "scene_type": "unknown",
    }
    result = await worker.process_one(msg)
    assert result is not None
    assert result["path"] == "agent"

    async with AsyncSession(db) as session:
        task = await session.get(Task, "agent-test-001")
        assert task is not None
        assert task.path_taken == "agent"
