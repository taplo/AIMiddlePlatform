# WebSocket 实时推送实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** WebSocket 实时推送分析结果、告警、系统事件给客户端

**Architecture:** Redis Pub/Sub 作为 Worker 与 API 进程间的消息桥梁——Worker 生产消息发布到 Redis 频道，API 进程的 ConnectionManager 订阅后扇出给所有 WebSocket 客户端

**Tech Stack:** FastAPI WebSocket, redis-py pub/sub, 现有 security 模块

## Global Constraints

- 单通道 `ws://host/ws?token=xxx`，消息体带 `type` 字段区分
- 认证复用现有 JWT / API Key 机制（URL Query token）
- 使用现有 project-level `redis_client` 实例
- 遵循现有项目结构：`src/ws/` 模块，`src/api/routes/ws.py` 路由
- 不引入新依赖

---

### Task 1: publish() 工具函数

**Files:**
- Modify: `src/core/redis_client.py:130-145`
- Create: `src/ws/__init__.py`
- Test: `tests/test_ws_publish.py`

**Interfaces:**
- Consumes: `redis_client.get_redis()` (existing async Redis singleton)
- Produces: `publish(channel: str, data: dict) -> None` — 序列化为 JSON 后发布

- [ ] **Step 1: Write the test**

Create `tests/test_ws_publish.py`:

```python
import pytest
from unittest.mock import AsyncMock, patch
from src.ws import publish


@pytest.mark.asyncio
async def test_publish_serializes_and_publishes():
    mock_redis = AsyncMock(spec=["publish"])
    with patch("src.ws.get_redis", return_value=mock_redis):
        await publish("ws:test", {"key": "value"})
    mock_redis.publish.assert_awaited_once_with(
        "ws:test", '{"key": "value"}'
    )


@pytest.mark.asyncio
async def test_publish_raises_on_redis_error():
    mock_redis = AsyncMock(spec=["publish"])
    mock_redis.publish.side_effect = ConnectionError("Redis down")
    with patch("src.ws.get_redis", return_value=mock_redis):
        with pytest.raises(ConnectionError):
            await publish("ws:test", {"key": "value"})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_ws_publish.py -v`
Expected: FAIL with "No module named 'src.ws'" or "function not defined"

- [ ] **Step 3: Write minimal implementation**

Create `src/ws/__init__.py`:

```python
import json
from src.core.redis_client import get_redis


async def publish(channel: str, data: dict) -> None:
    redis_conn = await get_redis()
    await redis_conn.publish(channel, json.dumps(data, default=str))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_ws_publish.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/ws/__init__.py tests/test_ws_publish.py
git commit -m "feat: add ws publish() utility for Redis Pub/Sub"
```

---

### Task 2: ConnectionManager

**Files:**
- Create: `src/ws/manager.py`
- Test: `tests/test_ws_manager.py`

**Interfaces:**
- Consumes: `publish(channel, data)` — not used here, this is the consumer side
- Produces: `ConnectionManager(redis_url: str)`, `connect(ws)`, `disconnect(ws)`, `start()`, `stop()`, `_broadcast(data: str)`

- [ ] **Step 1: Write the test**

Create `tests/test_ws_manager.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.ws.manager import ConnectionManager


@pytest.mark.asyncio
async def test_connect_adds_ws():
    mgr = ConnectionManager("redis://localhost")
    ws = MagicMock()
    await mgr.connect(ws)
    assert ws in mgr._connections
    assert ws.accept.called


@pytest.mark.asyncio
async def test_disconnect_removes_ws():
    mgr = ConnectionManager("redis://localhost")
    ws = MagicMock()
    await mgr.connect(ws)
    await mgr.disconnect(ws)
    assert ws not in mgr._connections


@pytest.mark.asyncio
async def test_broadcast_sends_to_all():
    mgr = ConnectionManager("redis://localhost")
    ws1 = MagicMock()
    ws2 = MagicMock()
    await mgr.connect(ws1)
    await mgr.connect(ws2)
    await mgr._broadcast('{"type": "test"}')
    ws1.send_text.assert_called_once_with('{"type": "test"}')
    ws2.send_text.assert_called_once_with('{"type": "test"}')


@pytest.mark.asyncio
async def test_broadcast_removes_dead_connections():
    mgr = ConnectionManager("redis://localhost")
    ws1 = MagicMock()
    ws2 = MagicMock()
    ws1.send_text.side_effect = Exception("dead")
    await mgr.connect(ws1)
    await mgr.connect(ws2)
    await mgr._broadcast('{"type": "test"}')
    assert ws1 not in mgr._connections
    assert ws2 in mgr._connections


@pytest.mark.asyncio
async def test_start_and_stop():
    mgr = ConnectionManager("redis://localhost")
    with patch.object(mgr, "_subscriber_loop", new_callable=AsyncMock) as mock_loop:
        with patch.object(mgr, "_redis", AsyncMock()) as mock_redis:
            await mgr.start()
            mock_loop.create_task.assert_called()
            await mgr.stop()
            mock_redis.close.assert_awaited()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_ws_manager.py -v`
Expected: FAIL with ImportError

- [ ] **Step 3: Write the implementation**

Create `src/ws/manager.py`:

```python
import asyncio
import json
import logging
from redis.asyncio import Redis
from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self, redis_url: str, ping_interval: int = 30):
        self._connections: list[WebSocket] = []
        self._redis_url = redis_url
        self._ping_interval = ping_interval
        self._redis: Redis | None = None
        self._subscriber_task: asyncio.Task | None = None

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._connections.append(ws)

    async def disconnect(self, ws: WebSocket) -> None:
        self._connections.remove(ws)

    async def start(self) -> None:
        self._redis = Redis.from_url(self._redis_url)
        self._subscriber_task = asyncio.create_task(self._subscriber_loop())

    async def stop(self) -> None:
        if self._subscriber_task:
            self._subscriber_task.cancel()
        if self._redis:
            await self._redis.close()

    async def _subscriber_loop(self) -> None:
        if not self._redis:
            return
        pubsub = self._redis.pubsub()
        await pubsub.subscribe("ws:analysis_result", "ws:alert", "ws:system_event")
        try:
            async for msg in pubsub.listen():
                if msg["type"] == "message":
                    await self._broadcast(msg["data"].decode("utf-8")
                                          if isinstance(msg["data"], bytes)
                                          else msg["data"])
        except asyncio.CancelledError:
            pass
        finally:
            await pubsub.unsubscribe()

    async def _broadcast(self, data: str) -> None:
        dead: list[WebSocket] = []
        for ws in self._connections:
            try:
                await ws.send_text(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            try:
                self._connections.remove(ws)
            except ValueError:
                pass
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_ws_manager.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/ws/manager.py tests/test_ws_manager.py
git commit -m "feat: add ConnectionManager for WebSocket fan-out"
```

---

### Task 3: WebSocket 认证

**Files:**
- Create: `src/ws/auth.py`
- Test: `tests/test_ws_auth.py`

**Interfaces:**
- Consumes: `security.verify_jwt_token(token: str)`, `security.api_key_store.validate(key: str)`
- Produces: `validate_ws_token(token: str) -> bool`

- [ ] **Step 1: Write the test**

Create `tests/test_ws_auth.py`:

```python
import pytest
from unittest.mock import patch, MagicMock
from src.ws.auth import validate_ws_token


def test_valid_jwt_token_returns_true():
    with patch("src.ws.auth.verify_jwt_token", return_value={"sub": "user1"}):
        result = validate_ws_token("valid_jwt_token")
    assert result is True


def test_invalid_jwt_and_api_key_returns_false():
    with patch("src.ws.auth.verify_jwt_token", return_value=None):
        result = validate_ws_token("invalid_token")
    assert result is False


def test_valid_api_key_returns_true():
    with patch("src.ws.auth.verify_jwt_token", return_value=None):
        with patch("src.ws.auth.api_key_store") as mock_store:
            mock_store.validate.return_value = True
            result = validate_ws_token("valid_api_key_abc123")
    assert result is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_ws_auth.py -v`
Expected: FAIL with ImportError

- [ ] **Step 3: Write the implementation**

Create `src/ws/auth.py`:

```python
from src.security import verify_jwt_token, api_key_store


def validate_ws_token(token: str) -> bool:
    if verify_jwt_token(token) is not None:
        return True
    if api_key_store.validate(token):
        return True
    return False
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_ws_auth.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/ws/auth.py tests/test_ws_auth.py
git commit -m "feat: add WebSocket token validation"
```

---

### Task 4: WebSocket 路由 + App 集成

**Files:**
- Create: `src/api/routes/ws.py`
- Modify: `src/api/routes/__init__.py` (register router)
- Modify: `src/api/app.py` (lifespan start/stop)
- Test: `tests/test_ws_integration.py`

**Interfaces:**
- Consumes: `ConnectionManager`, `validate_ws_token(token)`
- Produces: FastAPI WebSocket endpoint at `/ws`

- [ ] **Step 1: Write the integration test**

Create `tests/test_ws_integration.py`:

```python
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient
from src.api.app import app
from src.ws.manager import ConnectionManager


@pytest.fixture
def mock_manager():
    mgr = MagicMock(spec=ConnectionManager)
    mgr.connect = AsyncMock()
    mgr.disconnect = AsyncMock()
    return mgr


@pytest.mark.asyncio
async def test_ws_endpoint_valid_token_accepts(mock_manager):
    with patch("src.api.routes.ws.ws_manager", mock_manager):
        with patch("src.api.routes.ws.validate_ws_token", return_value=True):
            client = TestClient(app)
            with client.websocket_connect("/ws?token=valid") as ws:
                ws.send_text("ping")
                data = ws.receive_text()
                assert data is not None


@pytest.mark.asyncio
async def test_ws_endpoint_invalid_token_rejects():
    with patch("src.api.routes.ws.validate_ws_token", return_value=False):
        client = TestClient(app)
        with pytest.raises(Exception):  # WebSocket disconnect with 4001
            with client.websocket_connect("/ws?token=invalid") as ws:
                pass
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_ws_integration.py -v`
Expected: FAIL with ImportError (ws route not found)

- [ ] **Step 3: Create WebSocket route**

Create `src/api/routes/ws.py`:

```python
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, Depends
from src.ws.manager import ConnectionManager
from src.ws.auth import validate_ws_token
from src.config import config

logger = logging.getLogger(__name__)

router = APIRouter(tags=["websocket"])

ws_manager: ConnectionManager | None = None


def get_ws_manager() -> ConnectionManager:
    assert ws_manager is not None, "ConnectionManager not initialized"
    return ws_manager


@router.websocket("/ws")
async def websocket_endpoint(
    ws: WebSocket,
    token: str = Query(...),
    manager: ConnectionManager = Depends(get_ws_manager),
):
    if not validate_ws_token(token):
        await ws.close(code=4001)
        return
    await manager.connect(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(ws)
```

- [ ] **Step 4: Register the router**

Modify `src/api/routes/__init__.py` to add:

```python
from .ws import router as ws_router
api_router.include_router(ws_router)
```

- [ ] **Step 5: Wire ConnectionManager into app lifespan**

Modify `src/api/app.py`:

- On startup: read `websocket.enabled` and `websocket.ping_interval` from config, create `ConnectionManager`, call `manager.start()`, assign to `ws_manager`
- On shutdown: call `manager.stop()`
- Import `ws_manager` from routes.ws and assign it

- [ ] **Step 6: Run test to verify it passes**

Run: `pytest tests/test_ws_integration.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/api/routes/ws.py src/api/routes/__init__.py src/api/app.py tests/test_ws_integration.py
git commit -m "feat: add WebSocket endpoint with auth and app integration"
```

---

### Task 5: Worker 发布分析结果

**Files:**
- Modify: `src/worker.py` (`_save_result()` 末尾添加 publish)
- Test: `tests/test_worker_ws.py`

- [ ] **Step 1: Write the test**

Create `tests/test_worker_ws.py`:

```python
import pytest
from unittest.mock import patch, AsyncMock
from src.worker import process_task


@pytest.mark.asyncio
async def test_worker_publishes_analysis_result():
    task_data = {
        "task_id": "task-1",
        "camera_id": "cam-1",
        "timestamp": "2026-07-13T00:00:00",
    }
    with patch("src.worker.publish", new_callable=AsyncMock) as mock_pub:
        with patch("src.worker.redis_streams") as mock_redis:
            with patch("src.worker.inference_orchestrator") as mock_infer:
                mock_redis.xack = AsyncMock()
                mock_redis.xdel = AsyncMock()
                mock_infer.infer = AsyncMock(return_value={
                    "detections": [],
                    "model_id": "yolov8",
                    "inference_ms": 10,
                })
                mock_task = MagicMock()
                mock_task.task_id = "task-1"
                mock_task.camera_id = "cam-1"
                mock_task.status = "completed"
                mock_task.path_taken = "fast"
                with patch("src.worker.save_task_result", return_value=mock_task):
                    await process_task(task_data)
    mock_pub.assert_awaited()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_worker_ws.py -v`
Expected: FAIL (test structure)

- [ ] **Step 3: Modify worker.py**

In `_save_result()`, after saving to DB and returning `task_record`, publish `ws:analysis_result`:

```python
from src.ws import publish as ws_publish

# Inside _save_result(), after task_record = save_task_result(...):
if config.get("websocket.enabled", True):
    await ws_publish("ws:analysis_result", {
        "task_id": task_record.task_id,
        "camera_id": task_record.camera_id,
        "status": task_record.status,
        "path_taken": task_record.path_taken,
        "latency_ms": task_record.latency_ms,
        "detections": context.get("detections", []),
        "result": task_record.result,
    })
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_worker_ws.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/worker.py tests/test_worker_ws.py
git commit -m "feat: worker publishes analysis result via WebSocket"
```

---

### Task 6: 规则引擎发布告警

**Files:**
- Modify: `src/pipeline/rule_engine.py` (`create_alert()` 添加 publish)
- Test: `tests/test_rule_engine_ws.py`

- [ ] **Step 1: Write the test**

Create `tests/test_rule_engine_ws.py`:

```python
import pytest
from unittest.mock import patch, AsyncMock
from src.pipeline.rule_engine import evaluate_frame


@pytest.mark.asyncio
async def test_rule_engine_publishes_alert():
    with patch("src.pipeline.rule_engine.publish", new_callable=AsyncMock) as mock_pub:
        with patch("src.pipeline.rule_engine.db") as mock_db:
            with patch("src.pipeline.rule_engine.load_bindings", return_value=[]):
                # evaluate_frame with a detection that triggers a rule
                detections = [
                    {"class": "person", "confidence": 0.9,
                     "bbox": [0, 0, 100, 100], "track_id": 1}
                ]
                with patch("src.pipeline.rule_engine.load_rules", return_value=[
                    {"id": 1, "name": "test", "type": "count_threshold",
                     "config": {"min_count": 1, "max_count": None},
                     "enabled": True}
                ]):
                    with patch("src.pipeline.rule_engine.load_bindings_for_rule", return_value=[
                        {"id": 1, "camera_id": "cam-1", "scene_type": None, "enabled": True}
                    ]):
                        result = await evaluate_frame(
                            "cam-1", "scene", detections,
                            existing_alert_ids=[]
                        )
    mock_pub.assert_awaited()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_rule_engine_ws.py -v`
Expected: FAIL

- [ ] **Step 3: Modify rule_engine.py**

In `create_alert()` or where alert is saved, add publish:

```python
from src.ws import publish as ws_publish

# After alert = save_alert_to_db(...):
if config.get("websocket.enabled", True):
    await ws_publish("ws:alert", {
        "alert_id": alert.id,
        "rule_name": alert.rule_name,
        "camera_id": alert.camera_id,
        "severity": alert.severity,
        "message": alert.message,
    })
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_rule_engine_ws.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/rule_engine.py tests/test_rule_engine_ws.py
git commit -m "feat: rule engine publishes alerts via WebSocket"
```

---

### Task 7: 配置 + 完整验证

**Files:**
- Modify: `config/default.yaml` (websocket 配置段)
- Run full test suite

- [ ] **Step 1: Add config**

Append to `config/default.yaml`:

```yaml
websocket:
  enabled: true
  ping_interval: 30
  max_connections: 10000
```

- [ ] **Step 2: Run full test suite**

Run: `pytest --ignore=models/test_inference.py -v --tb=short`
Expected: all existing tests pass + 7 new tests pass

- [ ] **Step 3: Commit**

```bash
git add config/default.yaml
git commit -m "chore: add websocket config section"
```
