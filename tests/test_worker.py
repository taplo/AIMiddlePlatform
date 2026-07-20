import asyncio
import json

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.agent.client import QwenVLClient
from src.core.database import Task, init_db
from src.worker import Worker


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

    db_task = asyncio.create_task(worker._db_worker())
    await worker._db_queue.join()
    db_task.cancel()

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

    db_task = asyncio.create_task(worker._db_worker())
    await worker._db_queue.join()
    db_task.cancel()

    async with AsyncSession(db) as session:
        task = await session.get(Task, "agent-test-001")
        assert task is not None
        assert task.path_taken == "agent"


@pytest.mark.asyncio
async def test_worker_backends_drain_queue():
    db = await init_db("sqlite+aiosqlite:///:memory:")
    worker = Worker(db, max_concurrent=5, db_queue_size=10, rule_queue_size=10)

    await worker._db_queue.put(("t1", "cam1", {"path": "fast", "latency_ms": 50}))
    await worker._rule_queue.put(("t2", "cam2", {"path": "agent", "latency_ms": 1000}))

    db_task = asyncio.create_task(worker._db_worker())
    rule_task = asyncio.create_task(worker._rule_worker())

    await worker._db_queue.join()
    await worker._rule_queue.join()

    db_task.cancel()
    rule_task.cancel()

    async with AsyncSession(db) as session:
        from sqlalchemy import select
        tasks = (await session.execute(select(Task))).scalars().all()
        assert len(tasks) == 1
        assert tasks[0].id == "t1"


@pytest.mark.asyncio
async def test_worker_concurrent_dispatch():
    import httpx

    from src.agent.client import QwenVLClient

    db = await init_db("sqlite+aiosqlite:///:memory:")
    transport = httpx.MockTransport(lambda req: httpx.Response(200, json={
        "choices": [{"message": {
            "content": '{"scene_type": "unknown", "objects": [], "anomalies": [], "summary": "no fast path match"}',
            "role": "assistant",
        }}]
    }))
    worker = Worker(db, max_concurrent=5)
    worker.orchestrator.agent.llm = QwenVLClient(http_client=httpx.AsyncClient(transport=transport))

    db_task = asyncio.create_task(worker._db_worker())
    rule_task = asyncio.create_task(worker._rule_worker())

    msgs = [
        json.dumps({"task_id": f"concurrent-{i:03d}", "camera_id": "cam-test", "frame": "", "scene_type": "unknown"})
        for i in range(10)
    ]
    tasks = [asyncio.create_task(worker._process_with_semaphore(m)) for m in msgs]
    await asyncio.gather(*tasks)

    await worker._db_queue.join()
    await worker._rule_queue.join()
    db_task.cancel()
    rule_task.cancel()

    async with AsyncSession(db) as session:
        from sqlalchemy import select
        saved = (await session.execute(select(Task))).scalars().all()
        saved_ids = {t.id for t in saved}
        expected = {f"concurrent-{i:03d}" for i in range(10)}
        assert saved_ids == expected, f"Missing: {expected - saved_ids}"


@pytest.mark.asyncio
async def test_worker_backpressure_handling():
    """When queues are full, backpressure logs warning and skips without raising."""
    db = await init_db("sqlite+aiosqlite:///:memory:")
    worker = Worker(db, max_concurrent=10, db_queue_size=1, rule_queue_size=1)

    await worker._db_queue.put(("blocker", "cam1", {"path": "fast", "results": {}}))
    await worker._rule_queue.put(("blocker", "cam1", {"path": "fast", "results": {}}))

    import src.core.config as cfg
    original = cfg.settings.get("websocket.enabled", True)
    cfg.settings._config["websocket"] = {"enabled": False}
    try:
        await worker._enqueue_save("bp-test", "cam1", {"path": "fast", "latency_ms": 50, "results": {}})
    finally:
        cfg.settings._config["websocket"] = {"enabled": original}
