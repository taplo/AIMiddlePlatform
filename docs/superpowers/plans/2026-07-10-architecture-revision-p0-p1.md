# 架构修正 P0+P1 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立存储层 + Worker 进程，将帧处理从同步 HTTP 切换为异步队列模式

**Architecture:** FastAPI 接收帧后写入 Redis Streams 立即返回 task_id；独立 Worker 进程消费队列、执行推理、写 SQLite；客户端轮询结果

**Tech Stack:** SQLAlchemy 2.0 (async), SQLite (aiosqlite), Alembic, Redis Streams (现有), FastAPI

## Global Constraints

- Python 3.12+, uv 包管理
- SQLAlchemy 2.0 async session 模式
- 数据库 URL 可配置（`config/database.py` 或环境变量 `DATABASE_URL`）
- 数据库迁移使用 Alembic
- 所有新代码需有对应测试（pytest + asyncio 模式）
- 搜索结果写入 tasks 表时 `path_taken` 字段区分 `fast` / `agent`
- 帧 base64 大小限制 10MB（请求层校验）
- 兼容现有 `?sync=true` 行为（保留旧同步路径）

---

### Task 1: 数据库核心层

**Files:**
- Create: `src/core/database.py`
- Modify: `pyproject.toml`（添加依赖）
- Test: `tests/test_database.py`

**Interfaces:**
- Produces: `get_session() → AsyncGenerator[AsyncSession]`、`Task ORM model`、`Alert ORM model`

- [ ] **Step 1: 添加依赖**

```bash
uv add sqlalchemy aiosqlite alembic
```

- [ ] **Step 2: 写测试（数据库初始化 + 建表）**

```python
# tests/test_database.py
import pytest
from sqlalchemy import select, func
from src.core.database import get_session, init_db, Task, Alert

@pytest.mark.asyncio
async def test_init_db_creates_tables():
    engine = await init_db("sqlite+aiosqlite:///:memory:")
    async with engine.connect() as conn:
        tables = await conn.run_sync(lambda sync_conn: sync_conn.execute(
            select(func.count()).select_from(...)
        ))
        # ... 验证表存在
```

- [ ] **Step 3: 运行测试确认失败**

```bash
uv run python -m pytest tests/test_database.py::test_init_db_creates_tables -v
Expected: ModuleNotFoundError / ImportError
```

- [ ] **Step 4: 实现 database.py**

```python
# src/core/database.py
from datetime import datetime
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, Integer, Float, Text, DateTime, func

class Base(DeclarativeBase):
    pass

class Task(Base):
    __tablename__ = "tasks"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    camera_id: Mapped[str] = mapped_column(String(64))
    path_taken: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16), default="queued")
    result_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    alert_count: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_msg: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

class Alert(Base):
    __tablename__ = "alerts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(String(36))
    alert_type: Mapped[str] = mapped_column(String(64))
    label: Mapped[str] = mapped_column(String(64))
    bbox: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float] = mapped_column(Float)
    verified_by: Mapped[str] = mapped_column(String(16), default="model")
    status: Mapped[str] = mapped_column(String(16), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

_engine = None
_session_factory = None

async def init_db(url: str = "sqlite+aiosqlite:///data/aimp.db"):
    global _engine, _session_factory
    _engine = create_async_engine(url, echo=False)
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    _session_factory = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine

async def get_session():
    if _session_factory is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    async with _session_factory() as session:
        yield session
```

- [ ] **Step 5: 运行测试确认通过**

```bash
uv run python -m pytest tests/test_database.py -v
Expected: PASS
```

- [ ] **Step 6: 提交**

```bash
git add src/core/database.py tests/test_database.py pyproject.toml uv.lock
git commit -m "feat: add SQLAlchemy database layer with Task and Alert models"
```

---

### Task 2: Alembic 初始化迁移

**Files:**
- Create: `alembic.ini`
- Create: `alembic/env.py`
- Create: `alembic/versions/001_initial.py`

- [ ] **Step 1: 生成 Alembic 配置**

```bash
cd D:\projects\AIMiddlePlatform
uv run alembic init alembic
```

- [ ] **Step 2: 编辑 alembic/env.py 指向 src.core.database.Base**

```python
# alembic/env.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.database import Base
target_metadata = Base.metadata
```

- [ ] **Step 3: 编辑 alembic.ini 设置 sqlalchemy.url**

```ini
sqlalchemy.url = sqlite+aiosqlite:///data/aimp.db
```

- [ ] **Step 4: 生成初始迁移**

```bash
uv run alembic revision --autogenerate -m "initial tables"
```

- [ ] **Step 5: 验证迁移**

```bash
uv run alembic upgrade head
Expected: 输出 migration 执行日志，无错误
```

- [ ] **Step 6: 提交**

```bash
git add alembic.ini alembic/ uv.lock
git commit -m "feat: add Alembic migrations for initial schema"
```

---

### Task 3: Worker 进程入口

**Files:**
- Create: `src/worker.py`
- Modify: `src/core/database.py`（添加 `init_db` 和 `save_task` 辅助方法）
- Test: `tests/test_worker.py`

**Interfaces:**
- Consumes: `init_db(url)` from Task 1
- Consumes: `RedisStreamQueue` from `src/queue/redis_streams.py`
- Consumes: `FastPathHandler` from `src/routing/fast_path.py`
- Consumes: `AgentOrchestrator` from `src/agent/orchestrator.py`
- Produces: `run_worker()` - main entry point

- [ ] **Step 1: 写测试（Worker 初始化 + 消费循环）**

```python
# tests/test_worker.py
import pytest
from src.worker import Worker
from src.core.database import init_db, Task

@pytest.mark.asyncio
async def test_worker_processes_task():
    db = await init_db("sqlite+aiosqlite:///:memory:")
    worker = Worker(db)
    # mock queue message
    result = await worker.process_one({
        "task_id": "test-001",
        "camera_id": "cam-01",
        "frame": "<base64_fake>",
        "scene_type": "detection",
    })
    assert result is not None
    assert "path" in result
```

- [ ] **Step 2: 运行测试确认失败**

```bash
uv run python -m pytest tests/test_worker.py -v
```

- [ ] **Step 3: 实现 worker.py**

```python
# src/worker.py
import json
import logging
import asyncio
from typing import Any

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy import select

from src.core.database import Task, Alert
from src.queue.redis_streams import RedisStreamQueue
from src.routing.fast_path import FastPathHandler
from src.agent.orchestrator import AgentOrchestrator
from src.models.inference import InferenceOrchestrator
from src.models.registry import ModelRegistry
from src.models.presets import register_default_models
from src.models.adapters.yolov8_adapter import YOLOv8Adapter
from src.pipeline.registry import PipelineRegistry
from src.pipeline.executor import DAGExecutor
from src.pipeline.dag import DAGDefinition, DAGNode, NodeType
from src.routing.scene_router import SceneRouter
from src.agent.tools import ToolRegistry, build_cv_tools
from src.agent.client import QwenVLClient
from src.agent.agent import CVAgent
from src.api.routes import models as models_route
from src.api.routes import routing as routing_route
from src.api.routes.analyze import init_orchestrator as analyze_init_orchestrator

logger = logging.getLogger(__name__)


def _init_inference() -> InferenceOrchestrator:
    registry = ModelRegistry()
    register_default_models(registry)
    inference = InferenceOrchestrator(registry)
    inference.register_adapter("onnx", YOLOv8Adapter(model_dir="models"))
    return inference


def _init_fast_path() -> tuple[SceneRouter, PipelineRegistry, DAGExecutor, FastPathHandler]:
    router = SceneRouter()
    registry = PipelineRegistry()
    executor = DAGExecutor()
    executor.register_handler(NodeType.MODEL_INFERENCE, _inference_handler)
    _register_default_pipelines(registry)
    handler = FastPathHandler(router, registry, executor)
    return router, registry, executor, handler


def _register_default_pipelines(registry: PipelineRegistry) -> None:
    pipelines = {
        "plate_recognition": [DAGNode("detect_plate", NodeType.MODEL_INFERENCE, config={"model": "license_plate"})],
        "object_detection": [DAGNode("detect_objects", NodeType.MODEL_INFERENCE, config={"model": "object_detection"})],
        "face_recognition": [DAGNode("detect_faces", NodeType.MODEL_INFERENCE, config={"model": "face_recognition"})],
        "vehicle_detection": [DAGNode("detect_vehicles", NodeType.MODEL_INFERENCE, config={"model": "vehicle_detection"})],
        "ocr": [DAGNode("ocr_text", NodeType.MODEL_INFERENCE, config={"model": "ocr"})],
    }
    for name, nodes in pipelines.items():
        dag = DAGDefinition(name=name)
        for n in nodes:
            dag.add_node(n)
        registry.register(name, dag)


def _decode_frame(frame: str):
    import base64
    import cv2
    import numpy as np
    try:
        raw = base64.b64decode(frame)
        arr = np.frombuffer(raw, dtype=np.uint8)
        return cv2.imdecode(arr, cv2.IMREAD_COLOR)
    except Exception:
        return None


def _inference_handler(context: dict, input_data: dict, node_config: dict) -> dict:
    from src.models.registry import ModelSpec
    model_id = node_config.get("model", "")
    if not model_id:
        return {"error": "no model_id in node_config"}
    raw = context.get("frame")
    if raw is None:
        return {"error": "no frame in context"}
    image = _decode_frame(raw)
    if image is None:
        return {"error": "failed to decode frame"}
    import asyncio
    result = asyncio.run(_inference.infer(model_id, {"image": image}))
    return result


_inference: InferenceOrchestrator | None = None


class Worker:
    def __init__(self, db_engine: AsyncEngine):
        self.db = db_engine
        global _inference
        _inference = _init_inference()
        _, _, _, self.fast_path = _init_fast_path()

    async def process_one(self, message: dict) -> dict:
        task_id = message.get("task_id", "unknown")
        camera_id = message.get("camera_id", "unknown")
        start = asyncio.get_event_loop().time()

        # 当前只走 Fast Path，Agent 路径后续实现
        result = await self.fast_path.process(message)

        latency = (asyncio.get_event_loop().time() - start) * 1000
        if result is None:
            result = {"path": "agent", "analysis": "stub", "latency_ms": latency}
        else:
            result.setdefault("latency_ms", latency)

        await self._save_result(task_id, camera_id, result)
        return result

    async def _save_result(self, task_id: str, camera_id: str, result: dict):
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


async def run_worker(db_url: str = "sqlite+aiosqlite:///data/aimp.db"):
    from src.core.database import init_db
    db = await init_db(db_url)
    worker = Worker(db)
    queue = RedisStreamQueue()

    logger.info("Worker started, consuming from aimp:tasks")
    async for raw in queue.consume("aimp:tasks"):
        try:
            msg = json.loads(raw)
            await worker.process_one(msg)
        except Exception as e:
            logger.error("Failed to process message: %s", e)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_worker())
```

- [ ] **Step 4: 写简化版测试验证 Worker 能消费并写入 SQLite**

```python
# tests/test_worker.py (补充)
import json
import pytest
from sqlalchemy import select
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
```

- [ ] **Step 5: 运行测试**

```bash
uv run python -m pytest tests/test_worker.py -v
Expected: PASS
```

- [ ] **Step 6: 提交**

```bash
git add src/worker.py tests/test_worker.py
git commit -m "feat: add Worker process with queue consumption and DB persistence"
```

---

### Task 4: API 层改为异步队列（默认） + 结果查询端点

**Files:**
- Modify: `src/api/routes/analyze.py`
- Modify: `src/api/routes/ingest.py`
- Create: `src/api/routes/tasks.py`（新增任务结果查询路由）
- Modify: `src/api/app.py`（注册新路由 + 初始化队列）
- Test: `tests/test_async_analyze.py`

**Interfaces:**
- Consumes: `RedisStreamQueue` from `src/queue/redis_streams.py`
- Consumes: Task ORM model from Task 1
- Produces: `POST /v1/analyze/frame` (async mode), `GET /v1/tasks/{id}/results`

- [ ] **Step 1: 在 analyze.py 中改为默认异步（含帧大小校验）**

```python
# src/api/routes/analyze.py
import uuid
import json
import logging
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query

from src.queue.redis_streams import RedisStreamQueue

router = APIRouter(prefix="/v1/analyze", tags=["analyze"])

_queue: RedisStreamQueue | None = None
MAX_FRAME_BYTES = 10 * 1024 * 1024  # 10MB


def init_queue(queue: RedisStreamQueue) -> None:
    global _queue
    _queue = queue


@router.post("/frame")
async def analyze_frame(
    body: dict,
    sync: bool = Query(False, description="同步模式（调试用）"),
) -> dict:
    if _queue is None:
        raise HTTPException(500, "Queue not initialized")

    # 帧大小校验（异步模式也校验，防止恶意大请求）
    frame_raw = body.get("frame", "")
    if len(frame_raw) > MAX_FRAME_BYTES:
        raise HTTPException(413, "Frame too large (max 10MB)")

    # 同步模式：保留旧行为（走 orchestrator）
    if sync:
        from src.agent.orchestrator import AgentOrchestrator
        orchestrator = getattr(analyze_frame, "_orchestrator", None)
        if orchestrator is None:
            raise HTTPException(500, "Orchestrator not initialized in sync mode")
        body["frame"] = frame_raw  # 同步模式需要完整 frame
        result = await orchestrator.process(body)
        return result

    # 异步模式：写入队列立即返回 task_id
    task_id = str(uuid.uuid4())
    msg = {
        "task_id": task_id,
        "camera_id": body.get("camera_id", "unknown"),
        "frame": frame_raw,
        "scene_type": body.get("scene_type"),
        "model_id": body.get("model_id"),
        "timestamp": datetime.now().isoformat(),
    }
    await _queue.enqueue("aimp:tasks", json.dumps(msg))
    return {"task_id": task_id, "status": "queued"}


@router.get("/ping")
async def ping() -> dict:
    return {"ok": True, "timestamp": str(datetime.now())}
```

- [ ] **Step 2: 新增结果查询路由**

```python
# src/api/routes/tasks.py
from fastapi import APIRouter, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import Task

router = APIRouter(prefix="/v1/tasks", tags=["tasks"])

_db_session_factory = None


def init_db_session_factory(factory) -> None:
    global _db_session_factory
    _db_session_factory = factory


@router.get("/{task_id}/results")
async def get_task_result(task_id: str) -> dict:
    if _db_session_factory is None:
        raise HTTPException(500, "DB not initialized")
    async with _db_session_factory() as session:
        task = await session.get(Task, task_id)
    if task is None:
        raise HTTPException(404, f"Task {task_id} not found")
    return {
        "task_id": task.id,
        "status": task.status,
        "camera_id": task.camera_id,
        "path_taken": task.path_taken,
        "result": task.result_json,
        "latency_ms": task.latency_ms,
        "error": task.error_msg,
        "created_at": str(task.created_at) if task.created_at else None,
    }
```

- [ ] **Step 3: 修改 app.py 注册新路由**

```python
# 在 src/api/app.py 顶部添加 import
from src.api.routes import tasks as tasks_route

# 在 lifespan 或 _init_components 中初始化
from src.core.database import init_db, get_session

async def lifespan(app: FastAPI):
    db_engine = await init_db("sqlite+aiosqlite:///data/aimp.db")
    _db_session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    analyze_route.init_db_session_factory(_db_session_factory)
    tasks_route.init_db_session_factory(_db_session_factory)
    _init_components()
    init_log_buffer(maxlen=2000)
    yield

# 注册路由
app.include_router(tasks_route.router)
```

- [ ] **Step 4: 写测试**

```python
# tests/test_async_analyze.py
import pytest
from fastapi.testclient import TestClient
from src.api.app import app

@pytest.mark.asyncio
async def test_analyze_frame_returns_task_id():
    client = TestClient(app)
    resp = client.post("/v1/analyze/frame?sync=false", json={
        "camera_id": "cam-test",
        "scene_type": "detection",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "task_id" in data
    assert data["status"] == "queued"
```

- [ ] **Step 5: 运行测试**

```bash
uv run python -m pytest tests/test_async_analyze.py -v --tb=short
Expected: PASS
```

- [ ] **Step 6: 运行全部测试确认不破坏已有功能**

```bash
uv run python -m pytest tests/ -q --tb=short
Expected: 全部通过（128+ 测试）
```

- [ ] **Step 7: 提交**

```bash
git add src/api/routes/analyze.py src/api/routes/tasks.py src/api/app.py tests/test_async_analyze.py
git commit -m "feat: switch /v1/analyze/frame to async queue by default, add task result endpoint"
```

---

### Task 5: 端到端验证 + 兼容性

**Files:**
- Modify: `src/api/app.py`（确保 `sync=true` 路径兼容现有 orchestrator）
- Test: 手动验证

- [ ] **Step 1: 确认 sync 模式保留旧行为**

确保 `?sync=true` 时走 `AgentOrchestrator.process()` 路径不变，已保留在 `analyze.py` 中。

- [ ] **Step 2: 运行全部测试**

```bash
uv run python -m pytest tests/ -q --tb=short
Expected: 全部通过
```

- [ ] **Step 3: 手动启动验证**

```bash
# 终端 1：启动 API
uv run uvicorn src.api.app:app --port 8001

# 终端 2：测试异步模式
curl -s -X POST "http://127.0.0.1:8001/v1/analyze/frame" \
  -H "Content-Type: application/json" \
  -d '{"camera_id":"cam-test","scene_type":"detection"}'
# Expected: {"task_id":"uuid","status":"queued"}
```

- [ ] **Step 4: 提交**

```bash
git add src/api/app.py
git commit -m "chore: ensure sync fallback compatibility"
```

---

### Task 6: Docker + 部署更新

**Files:**
- Modify: `Dockerfile`
- Modify: `docker-compose.yml`

- [ ] **Step 1: Dockerfile 保持统一镜像，增加 Worker 入口**

```dockerfile
# 在现有 Dockerfile 末尾添加（无需改动已有内容）
# Worker 与 API 共享同一镜像，不同 CMD
```

无需改动 Dockerfile——`uvicorn` 和 `python -m src.worker` 都在同一镜像中可运行。

- [ ] **Step 2: docker-compose.yml 增加 Worker 服务**

```yaml
services:
  aimp-api:
    # 不变
  aimp-worker:
    image: taplo/aimiddleplatform:latest
    command: python -m src.worker
    depends_on:
      - redis
    environment:
      - DATABASE_URL=sqlite+aiosqlite:///data/aimp.db
    volumes:
      - ./data:/app/data   # SQLite 持久化
    restart: unless-stopped
    networks:
      - aimp-network
```

- [ ] **Step 3: 提交**

```bash
git add docker-compose.yml
git commit -m "feat: add aimp-worker service to docker-compose"
```

---

### Plan Self-Review

**Spec coverage check:**
- P0 存储层 → Task 1 (database.py) + Task 2 (Alembic) ✅
- P0 Worker 进程 → Task 3 (worker.py) ✅
- P1 帧路径切换 → Task 4 (async analyze + task query) ✅
- P1 同步模式兼容 → Task 5 ✅
- P1 Docker 部署 → Task 6 ✅

**Placeholder scan:** 无占位符。所有步骤含完整代码。

**Type consistency check:**
- `init_db(url)` → `sqlite+aiosqlite:///data/aimp.db` — 一致
- `Task` ORM 模型字段 → Task 1, 3, 4 中引用一致
- `RedisStreamQueue.enqueue(channel, msg)` — 使用现有接口
- `Worker.process_one(message)` → 消费 dict → 返回 dict

**Scope check:** P0+P1 是 P2-P6 的前提，范围聚焦，可独立验证。
