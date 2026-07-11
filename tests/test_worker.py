import json
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.database import init_db, Task
from src.worker import Worker


@pytest.mark.asyncio
async def test_worker_processes_and_saves():
    db = await init_db("sqlite+aiosqlite:///:memory:")
    worker = Worker(db)
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
