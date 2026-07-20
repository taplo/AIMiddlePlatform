# Worker 并发吞吐优化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Worker serial processing with semaphore-bounded concurrency + write-operation queue decoupling to enable 3-5x throughput under 1000+ camera load.

**Architecture:** Main consume loop creates async tasks bounded by `asyncio.Semaphore(N)`. DB writes and rule evaluations are pushed to bounded `asyncio.Queue`s drained by dedicated background workers. OpenCV decode offloaded to `asyncio.to_thread()` to avoid blocking event loop.

**Tech Stack:** Python 3.12+, asyncio, SQLAlchemy 2.x async, Prometheus client

## Global Constraints

- `max_concurrent` default: 10
- `db_queue_size` default: 200
- `rule_queue_size` default: 200
- Backpressure: `put_nowait` → fallback `wait_for(put, timeout=5)` → skip on timeout
- All metrics (`worker_tasks_total`, `worker_tasks_latency`) must remain intact
- Existing tests (test_worker_processes_and_saves, test_worker_falls_through_to_agent) must keep passing

---

### Task 1: Config + Worker Init + Backend Workers

**Files:**
- Modify: `config/default.yaml:48` — add `worker:` section
- Modify: `config/production.yaml:33` — add `worker:` section
- Modify: `src/worker.py:180-190` — expand `__init__`, add `_db_worker()` and `_rule_worker()`
- Modify: `src/core/config.py:6` — add `worker.*` env key mappings
- Test: `tests/test_worker.py:65+` — add `test_worker_backends`

**Interfaces:**
- Consumes: existing `Worker(db)` constructor, `config/default.yaml` format
- Produces: `Worker._db_queue`, `Worker._rule_queue` (asyncio.Queue), `Worker._db_worker()`, `Worker._rule_worker()` coroutines

- [ ] **Step 1: Add worker config to default.yaml**

```yaml
# append after line 47 (websocket.max_connections)
worker:
  max_concurrent: 10
  db_queue_size: 200
  rule_queue_size: 200
```

- [ ] **Step 2: Add env key mappings in config.py**

Edit `src/core/config.py`:

```python
_ENV_KEY_MAP: dict[str, str] = {
    ...
    "worker.max_concurrent": "WORKER_MAX_CONCURRENT",
    "worker.db_queue_size": "WORKER_DB_QUEUE_SIZE",
    "worker.rule_queue_size": "WORKER_RULE_QUEUE_SIZE",
}
```

- [ ] **Step 3: Expand Worker.__init__ with queues and semaphore**

Edit `src/worker.py` Worker class. Add import for `asyncio.Queue`, then modify `__init__`:

```python
class Worker:
    def __init__(self, db_engine: AsyncEngine, max_concurrent: int = 10, db_queue_size: int = 200, rule_queue_size: int = 200):
        self.db = db_engine
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._db_queue: asyncio.Queue = asyncio.Queue(maxsize=db_queue_size)
        self._rule_queue: asyncio.Queue = asyncio.Queue(maxsize=rule_queue_size)
        global _inference
        _inference = _init_inference()
        _, _, _, self.fast_path = _init_fast_path()
        tool_registry = ToolRegistry(_inference)
        build_cv_tools(tool_registry)
        agent = CVAgent(QwenVLClient(), tool_registry)
        self.orchestrator = AgentOrchestrator(self.fast_path, agent, _inference)
```

- [ ] **Step 4: Implement _db_worker()**

Add to `Worker` class after `__init__`:

```python
    async def _db_worker(self) -> None:
        while True:
            task_id, camera_id, result = await self._db_queue.get()
            try:
                import json
                async with AsyncSession(self.db) as session:
                    task = Task(
                        id=task_id,
                        camera_id=camera_id,
                        path_taken=result.get("path", "unknown"),
                        status="completed",
                        result_json=json.dumps(result, default=str),
                        latency_ms=int(result.get("latency_ms", 0)),
                    )
                    session.add(task)
                    await session.commit()
            except Exception:
                logger.exception("_db_worker: failed for task %s camera %s", task_id, camera_id)
            finally:
                self._db_queue.task_done()
```

- [ ] **Step 5: Implement _rule_worker()**

Add to `Worker` class:

```python
    async def _rule_worker(self) -> None:
        eval_sem = asyncio.Semaphore(2)
        while True:
            task_id, camera_id, result = await self._rule_queue.get()
            try:
                async with eval_sem:
                    await _evaluate_rules_for_task(self.db, task_id, camera_id, result)
            except Exception:
                logger.exception("_rule_worker: failed for task %s", task_id)
            finally:
                self._rule_queue.task_done()
```

- [ ] **Step 6: Write failing test for backend workers**

Add to `tests/test_worker.py`:

```python
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
```

- [ ] **Step 7: Run test to verify it fails**

Run: `uv run pytest tests/test_worker.py::test_worker_backends_drain_queue -v --tb=short`
Expected: FAIL — implementation not yet added (or PASS if you wrote it correctly)

- [ ] **Step 8: Run to verify**

Run: `uv run pytest tests/test_worker.py::test_worker_backends_drain_queue -v --tb=short`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add config/default.yaml config/production.yaml src/worker.py src/core/config.py tests/test_worker.py
git commit -m "perf: add worker queue backends + config"
```

---

### Task 2: process_one() Refactor + run_worker() Concurrency

**Files:**
- Modify: `src/worker.py:191-258` — refactor `process_one()`, `_save_result()`, add `_process_with_semaphore()`, update `run_worker()`
- Test: `tests/test_worker.py`
- Verify: existing tests still pass

**Interfaces:**
- Consumes: `Worker._db_queue`, `Worker._rule_queue`, `Worker._semaphore` from Task 1
- Produces: concurrent `run_worker()` loop with background workers

- [ ] **Step 1: Refactor process_one() — offload decode, queue DB/rules**

Replace `process_one()` and `_save_result()` in `src/worker.py`:

```python
    async def process_one(self, message: dict) -> dict:
        task_id = message.get("task_id", "unknown")
        camera_id = message.get("camera_id", "unknown")
        start = asyncio.get_event_loop().time()

        frame_raw = message.get("frame", "")
        image = await asyncio.to_thread(_decode_frame, frame_raw) if frame_raw else None

        result = await self.fast_path.process(message)

        latency = (asyncio.get_event_loop().time() - start) * 1000
        worker_tasks_total.labels(status="success" if result is not None else "error").inc()
        worker_tasks_latency.observe(latency / 1000)
        if result is None:
            result = await self.orchestrator.agent.analyze(message, image_data=image)
            result.setdefault("latency_ms", latency)
        else:
            result.setdefault("latency_ms", latency)

        if image is not None:
            try:
                cache = get_video_cache()
                cache.push(camera_id, image, task_id=task_id, metadata={
                    "path": result.get("path", "unknown"),
                    "detection_count": len(result.get("results", {}).get("detections", [])) if isinstance(result.get("results"), dict) else 0,
                })
            except Exception:
                logger.warning("Failed to cache frame for %s", camera_id)

        await self._enqueue_save(task_id, camera_id, result)
        return result

    async def _enqueue_save(self, task_id: str, camera_id: str, result: dict) -> None:
        # WS publish stays synchronous in process_one (needs real-time)
        import json
        if settings.get("websocket.enabled", True):
            detections = []
            if isinstance(result, dict):
                all_dets = result.get("all_detections", [])
                if all_dets and isinstance(all_dets, list):
                    detections = all_dets
                else:
                    for v in result.values():
                        if isinstance(v, dict) and "detections" in v:
                            detections.extend(v["detections"])
            await ws_publish("ws:analysis_result", {
                "task_id": task_id,
                "camera_id": camera_id,
                "status": "completed",
                "path_taken": result.get("path", "unknown"),
                "latency_ms": int(result.get("latency_ms", 0)),
                "detections": detections,
                "result": result,
            })

        # DB save via queue with backpressure
        entry = (task_id, camera_id, result)
        try:
            self._db_queue.put_nowait(entry)
        except asyncio.QueueFull:
            try:
                await asyncio.wait_for(self._db_queue.put(entry), timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning("db_queue full, skipping DB save for task %s camera %s", task_id, camera_id)

        # Rule eval via queue with backpressure
        try:
            self._rule_queue.put_nowait(entry)
        except asyncio.QueueFull:
            try:
                await asyncio.wait_for(self._rule_queue.put(entry), timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning("rule_queue full, skipping rule eval for task %s camera %s", task_id, camera_id)
```

- [ ] **Step 2: Add _process_with_semaphore wrapper**

Add to `Worker` class:

```python
    async def _process_with_semaphore(self, raw: str) -> None:
        async with self._semaphore:
            try:
                msg = json.loads(raw)
                await self.process_one(msg)
            except Exception:
                logger.exception("Failed to process message")
```

- [ ] **Step 3: Update run_worker()**

Replace `run_worker()`:

```python
async def run_worker(db_url: str = "sqlite+aiosqlite:///data/aimp.db"):
    _start_metrics_server()
    from src.core.database import init_db
    db = await init_db(db_url)
    worker = Worker(
        db,
        max_concurrent=settings.get("worker.max_concurrent", 10),
        db_queue_size=settings.get("worker.db_queue_size", 200),
        rule_queue_size=settings.get("worker.rule_queue_size", 200),
    )
    queue = RedisStreamQueue()

    asyncio.create_task(worker._db_worker(), name="db-worker")
    asyncio.create_task(worker._rule_worker(), name="rule-worker")

    logger.info("Worker started (max_concurrent=%d), consuming from aimp:tasks", worker._semaphore._value)
    async for raw in queue.consume("aimp:tasks"):
        asyncio.create_task(worker._process_with_semaphore(raw))
```

- [ ] **Step 4: Verify existing tests still pass**

Run: `uv run pytest tests/test_worker.py -v --tb=short`
Expected: 3 passed (test_worker_processes_and_saves, test_worker_falls_through_to_agent, test_worker_backends_drain_queue)

- [ ] **Step 5: Commit**

```bash
git add src/worker.py
git commit -m "perf: concurrent worker dispatch via semaphore + queue backpressure"
```

---

### Task 3: Concurrency + Backpressure Tests

**Files:**
- Test: `tests/test_worker.py` — add tests

- [ ] **Step 1: Add concurrent task dispatch test**

Add to `tests/test_worker.py`:

```python
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
```

- [ ] **Step 2: Add backpressure test**

Add to `tests/test_worker.py`:

```python
@pytest.mark.asyncio
async def test_worker_db_backpressure():
    db = await init_db("sqlite+aiosqlite:///:memory:")
    worker = Worker(db, max_concurrent=10, db_queue_size=1, rule_queue_size=100)

    # Fill the queue so next put triggers backpressure
    await worker._db_queue.put(("blocker", "cam1", {"path": "fast"}))
    # Use a minimal result dict without ws_publish dependency by calling _enqueue_save directly
    result = {"path": "fast", "latency_ms": 50, "results": {}}
    # Should not raise — backpressure should log and skip
    worker._enqueue_save("bp-test", "cam1", result)
    # Queue should still have the blocker (worker not draining)
    assert worker._db_queue.qsize() == 2  # blocker + skipped (actually it blocks then times out)
```

Wait, that test is wrong. Let me think about this.

Actually, `_enqueue_save` calls `ws_publish` which needs mocks. Let me redesign the test.

Better approach — test the backpressure behavior directly:

```python
@pytest.mark.asyncio
async def test_worker_db_backpressure_skips_on_timeout():
    db = await init_db("sqlite+aiosqlite:///:memory:")
    worker = Worker(db, max_concurrent=10, db_queue_size=1, rule_queue_size=100)

    # Fill the queue completely
    await worker._db_queue.put(("blocker", "cam1", {"path": "fast"}))

    # Queue is full — put_nowait should raise QueueFull, wait_for should timeout (no consumer)
    entry = ("bp-test", "cam1", {"path": "fast"})
    try:
        worker._db_queue.put_nowait(entry)
        assert False, "Expected QueueFull"
    except asyncio.QueueFull:
        pass

    # _enqueue_save should skip DB save on timeout
    result = {"path": "fast", "latency_ms": 50, "results": {}}
    with unittest.mock.patch.object(worker._db_queue, "put", wraps=worker._db_queue.put) as spy:
        await worker._enqueue_save("bp-test", "cam1", result)
        # should not raise
```

Hmm, this is getting complex. Let me simplify: test the _enqueue_save method with a full queue, verifying it doesn't crash.

Actually let me look at what ws_publish does - it sends to a websocket - and in test context this might fail. Let me check what happens when websocket is disabled.

Looking at _save_result, line 237: `if settings.get("websocket.enabled", True):` — it checks this setting.

For the test, I should mock ws_publish or set websocket.enabled to False. Or better yet, just test the queue behavior directly without _enqueue_save.

Let me write simpler, more focused tests.

- [ ] **Step 2: Add backpressure test**

Add to `tests/test_worker.py`:

```python
@pytest.mark.asyncio
async def test_worker_backpressure_handling():
    """When queues are full, backpressure logs warning and skips without raising."""
    db = await init_db("sqlite+aiosqlite:///:memory:")
    worker = Worker(db, max_concurrent=10, db_queue_size=1, rule_queue_size=1)

    # Fill both queues
    await worker._db_queue.put(("blocker", "cam1", {"path": "fast", "results": {}}))
    await worker._rule_queue.put(("blocker", "cam1", {"path": "fast", "results": {}}))

    # Calling _enqueue_save with full queues should not raise
    # WS publish is mocked via settings
    import src.core.config as cfg
    original = cfg.settings.get("websocket.enabled", True)
    cfg.settings._config["websocket"] = {"enabled": False}
    try:
        await worker._enqueue_save("bp-test", "cam1", {"path": "fast", "latency_ms": 50, "results": {}})
    finally:
        cfg.settings._config["websocket"] = {"enabled": original}
```

- [ ] **Step 3: Run all worker tests**

Run: `uv run pytest tests/test_worker.py -v --tb=short`
Expected: 5 passed

- [ ] **Step 4: Run full test suite**

Run: `uv run pytest tests/ --tb=short`
Expected: all existing tests pass (new + old)

- [ ] **Step 5: Commit**

```bash
git add tests/test_worker.py
git commit -m "test: add worker concurrency and backpressure tests"
```

---

### Task 4: Add worker config to production.yaml

**Files:**
- Modify: `config/production.yaml:33`

- [ ] **Step 1: Add worker section to production.yaml**

```yaml
worker:
  max_concurrent: 10
  db_queue_size: 200
  rule_queue_size: 200
```

- [ ] **Step 2: Commit**

```bash
git add config/production.yaml
git commit -m "config: add worker concurrency settings for production"
```

---

### Task 5: Final Verification + Integration

- [ ] **Step 1: Full test suite**

Run: `uv run pytest tests/ -v --tb=short`
Expected: 324+ passed, 2 skipped

- [ ] **Step 2: Lint check**

Run: `uv run ruff check src/worker.py tests/test_worker.py`
Expected: no errors

- [ ] **Step 3: Verify metrics unchanged**

Check that worker still exports `worker_tasks_total` and `worker_tasks_latency`:
```bash
uv run python -c "from src.worker import worker_tasks_total, worker_tasks_latency; print('metrics OK')"
```
Expected: `metrics OK`
