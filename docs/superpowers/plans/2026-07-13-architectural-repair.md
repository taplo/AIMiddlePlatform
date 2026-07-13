# 架构修复实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 解决 25 个已识别的架构问题，大重构修复 Agent 层 3 个致命 bug + 配置/DI/缓存/资源/API 规范改进

**Architecture:** 6 个工作包以 1 次 big-bang 提交完成；WP2（配置）→ WP1（Agent）→ WP3（DI）→ WP4（缓存）→ WP5（资源）→ WP6（路由+限流）；按依赖关系排序

**Tech Stack:** Python 3.12+, FastAPI, SQLAlchemy async, Redis async, asyncio, httpx, opencv-python-headless

## 全局不变约束

- 所有变量通过 `os.getenv("KEY", "default")` 读取环境变量
- 测试使用 SQLite（无 MySQL 依赖）
- Dockerfile 使用 `uvicorn src.api.app:app` 启动
- OpenCV 5.x 兼容（opencv-python-headless>=4.10.0.84 解析为 5.0.0.93）
- 不引入 pydantic-settings 等新依赖
- 不改动已有 304 个测试的通过率；修改的测试语义不变

---

## 文件结构

| 操作 | 路径 | 职责 |
|------|------|------|
| 修改 | `src/core/config.py` | 三分层 Settings：环境变量 → YAML → 默认值 |
| 删除 | `src/core/config_manager.py` | 被统一 Settings 替代 |
| 修改 | `src/api/routes/config_routes.py` | 从 config_manager 迁移到 Settings |
| 删除 | `tests/test_config_manager.py` | ConfigManager 测试被 Settings 测试替代 |
| 新增 | `tests/test_config.py` | Settings 测试 |
| 修改 | `src/pipeline/executor.py` | async/sync 自动分派 |
| 修改 | `src/pipeline/verify_handler.py` | 纯 async 改写 + ResultCache 统一 + 并行 LLM |
| 修改 | `tests/test_verify.py` | async 化 |
| 修改 | `tests/test_verify_cache.py` | async 化 |
| 修改 | `src/worker.py` | 补充 AGGREGATE/CONDITION handler 注册 |
| 修改 | `src/agent/orchestrator.py` | 消除双重 fast path |
| 修改 | `src/agent/tools.py` | base64 → numpy 管线 |
| 修改 | `src/agent/client.py` | HTTP 客户端 `aclose()` 生命周期 |
| 新增 | `src/api/deps.py` | `get_db()` 统一依赖注入 |
| 新增 | `src/pipeline/shared_init.py` | API/Worker 共用初始化 |
| 修改 | `src/api/app.py` | 使用 get_db + shared_init，路由前缀规范化 |
| 修改 | `src/api/routes/analyze.py` | `Depends(get_db)` 替代全局 |
| 修改 | `src/api/routes/tasks.py` | `Depends(get_db)` 替代全局 |
| 修改 | `src/api/routes/alerts.py` | `Depends(get_db)` 替代全局 |
| 修改 | `src/api/routes/admin_rules.py` | `Depends(get_db)` 替代全局 |
| 修改 | `src/pipeline/condition_handler.py` | `Depends(get_db)` 替代全局 |
| 修改 | `src/core/redis_client.py` | 连接重试 + 优雅降级 |
| 修改 | `src/ingestion/video_cache.py` | JPEG 压缩存储 + 全局内存上限 |
| 修改 | `src/models/inference.py` | LRU 会话上限 |
| 修改 | `src/core/security.py` | Redis 后端限流器 |
| 修改 | `src/api/routes/health.py` | 前缀 `/api/v1/health` |
| 修改 | `src/api/routes/ws.py` | 前缀 `/api/v1/ws` |
| 修改 | `src/api/routes/ingest.py` | 前缀 `/api/v1` |
| 修改 | `src/api/routes/models.py` | 前缀 `/api/v1/models` |
| 修改 | `src/api/routes/routing.py` | 前缀 `/api/v1/routing` |
| 修改 | `src/api/routes/video_cache.py` | 前缀 `/api/v1/video-cache` |
| 修改 | `src/api/routes/api_keys.py` | 前缀 `/api/v1/admin/api-keys` |
| 修改 | `deploy/nginx.conf` | 单条 location `/api/v1/` |
| 新增 | `tests/test_executor_async.py` | async handler 分派测试 |

---

### 任务 1: 配置系统统一（WP2）

**Files:**
- Modify: `src/core/config.py`
- Delete: `src/core/config_manager.py`
- Modify: `src/api/routes/config_routes.py`
- Create: `tests/test_config.py`
- Delete: `tests/test_config_manager.py`

**Interfaces:**
- Consumes: `config/default.yaml`, `config/production.yaml` (保持不变)
- Produces: `Settings.get(key, default)` 支持点号路径 + 环境变量覆盖

**Key decisions:**
- `_ENV_KEY_MAP` 维护配置键到环境变量名的显式映射
- 优先级：环境变量 > production.yaml > default.yaml
- 不删除 YAML 文件（保留为镜像内默认值）

- [ ] **Step 1: 重写 `src/core/config.py`**

```python
import os
from pathlib import Path

import yaml


_ENV_KEY_MAP: dict[str, str] = {
    "queue.redis_url": "QUEUE_REDIS_URL",
    "database.url": "DATABASE_URL",
    "llm.api_key": "LLM_API_KEY",
    "llm.api_url": "LLM_API_URL",
    "llm.model_name": "LLM_MODEL_NAME",
    "storage.endpoint": "S3_ENDPOINT",
    "storage.access_key": "S3_ACCESS_KEY",
    "storage.secret_key": "S3_SECRET_KEY",
    "storage.bucket": "S3_BUCKET",
    "result_cache.ttl_seconds": "CACHE_TTL_SECONDS",
    "result_cache.enabled": "CACHE_ENABLED",
    "websocket.enabled": "WS_ENABLED",
    "websocket.max_connections": "WS_MAX_CONNECTIONS",
    "app.env": "APP_ENV",
    "ingestion.max_streams": "MAX_STREAMS",
    "rate_limiter.default_rate": "RATE_LIMIT_DEFAULT",
}


class Settings:
    def __init__(self) -> None:
        self._config: dict = {}
        self._load()

    def _load(self) -> None:
        env = os.getenv("APP_ENV", "dev")
        config_dir = Path(__file__).parent.parent.parent / "config"
        default_path = config_dir / "default.yaml"
        env_path = config_dir / f"{env}.yaml"

        if default_path.exists():
            with open(default_path) as f:
                self._config.update(yaml.safe_load(f) or {})
        if env_path.exists():
            with open(env_path) as f:
                env_config = yaml.safe_load(f) or {}
                self._deep_merge(self._config, env_config)

    def _deep_merge(self, base: dict, overlay: dict) -> None:
        for key, value in overlay.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._deep_merge(base[key], value)
            else:
                base[key] = value

    def get(self, key: str, default=None):
        env_var = _ENV_KEY_MAP.get(key)
        if env_var:
            env_value = os.getenv(env_var)
            if env_value is not None:
                return self._coerce(env_value)
        keys = key.split(".")
        value = self._config
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default
        if value is None:
            return default
        return value

    @staticmethod
    def _coerce(value: str):
        if value.lower() in ("true", "1", "yes"):
            return True
        if value.lower() in ("false", "0", "no"):
            return False
        try:
            return int(value)
        except ValueError:
            pass
        try:
            return float(value)
        except ValueError:
            pass
        return value


settings = Settings()
```

- [ ] **Step 2: 重写 `config_routes.py` 使用 Settings**

```python
from fastapi import APIRouter

from src.core.config import settings

router = APIRouter(prefix="/api/v1/config", tags=["config"])


@router.get("")
async def get_config(section: str | None = None) -> dict:
    if section:
        val = settings.get(section)
        return {section: val} if val else {}
    return {}
```

- [ ] **Step 3: 删除 `src/core/config_manager.py`**

移除整个文件。

- [ ] **Step 4: 删除 `tests/test_config_manager.py`**

移除整个文件。

- [ ] **Step 5: 新建 `tests/test_config.py`**

```python
from src.core.config import settings


def test_get_existing_key():
    val = settings.get("app.version")
    assert val == "0.1.0"


def test_get_missing_key():
    assert settings.get("nonexistent.key") is None


def test_get_with_default():
    assert settings.get("nonexistent", 42) == 42


def test_get_section():
    val = settings.get("ingestion")
    assert isinstance(val, dict)
    assert val["max_streams"] == 1000
```

- [ ] **Step 6: 确认测试通过后提交**

```bash
git add src/core/config.py src/core/config_manager.py src/api/routes/config_routes.py tests/test_config.py tests/test_config_manager.py
git rm src/core/config_manager.py tests/test_config_manager.py
git commit -m "feat(core): unify Settings with env var support, remove ConfigManager"
```

---

### 任务 2: DAG Executor async/sync 自动分派（WP1a）

**Files:**
- Modify: `src/pipeline/executor.py`
- Modify: `tests/test_dag.py`
- Create: `tests/test_executor_async.py`

**Interfaces:**
- Produces: `DAGExecutor.execute()` 自动检测 handler 类型

**Key decisions:**
- `inspect.iscoroutinefunction()` 做运行时检测
- async handler 直接 `await`，sync handler 通过 `asyncio.to_thread()`
- 不改变任何调用者接口

- [ ] **Step 1: 修改 `executor.py` 的 `execute` 方法**

编辑 `src/pipeline/executor.py`，修改 `run()` 闭包：

```python
import inspect
# ... (other imports stay the same)

async def execute(self, dag: DAGDefinition, context: dict[str, Any]) -> dict[str, Any]:
    start = time.monotonic()
    results: dict[str, Any] = {}
    completed: set[str] = set()
    pending = set(dag.nodes.keys())

    while pending:
        ready = [
            nid for nid in pending
            if all(dep in completed for dep in dag.nodes[nid].depends_on)
        ]
        if not ready:
            logger.error("Cycle detected in DAG %s", dag.name)
            break

        tasks = []
        for nid in ready:
            node = dag.nodes[nid]
            handler = self._handlers.get(node.node_type)
            if handler is None:
                logger.warning("No handler for %s (%s)", nid, node.node_type)
                results[nid] = None
                completed.add(nid)
                pending.discard(nid)
                continue

            async def run(nid: str, handler: NodeHandler) -> None:
                input_data = {dep: results[dep] for dep in dag.nodes[nid].depends_on}
                if inspect.iscoroutinefunction(handler):
                    result = await handler(context, input_data, dag.nodes[nid].config)
                else:
                    result = await asyncio.to_thread(handler, context, input_data, dag.nodes[nid].config)
                results[nid] = result
                completed.add(nid)

            tasks.append(run(nid, handler))

        await asyncio.gather(*tasks)
        for nid in ready:
            pending.discard(nid)

    elapsed = time.monotonic() - start
    logger.info("DAG %s executed in %.0fms", dag.name, elapsed * 1000)
    try:
        from src.monitoring.metrics import dag_execution_total, dag_execution_latency
        dag_execution_total.labels(dag_name=dag.name, status="success").inc()
        dag_execution_latency.labels(dag_name=dag.name).observe(elapsed)
    except Exception:
        pass
    return results
```

- [ ] **Step 2: 新建 `tests/test_executor_async.py`**

```python
import pytest

from src.pipeline.dag import DAGDefinition, DAGNode, NodeType
from src.pipeline.executor import DAGExecutor


@pytest.mark.asyncio
async def test_executor_async_handler() -> None:
    dag = DAGDefinition(name="async_test")
    dag.add_node(DAGNode(node_id="step1", node_type=NodeType.CONDITION))
    dag.add_node(DAGNode(
        node_id="output", node_type=NodeType.OUTPUT, depends_on=["step1"]
    ))
    dag.entry_nodes = ["step1"]

    executor = DAGExecutor()

    async def async_handler(ctx, inp, cfg):
        return {"from_async": True}

    executor.register_handler(NodeType.CONDITION, async_handler)
    executor.register_handler(NodeType.OUTPUT, lambda ctx, inp, cfg: inp)

    results = await executor.execute(dag, {})
    assert results["step1"]["from_async"] is True


@pytest.mark.asyncio
async def test_executor_mixed_handlers() -> None:
    dag = DAGDefinition(name="mixed_test")
    dag.add_node(DAGNode(node_id="sync_step", node_type=NodeType.MODEL_INFERENCE))
    dag.add_node(DAGNode(
        node_id="async_step", node_type=NodeType.VERIFY, depends_on=["sync_step"]
    ))
    dag.entry_nodes = ["sync_step"]

    executor = DAGExecutor()
    executor.register_handler(NodeType.MODEL_INFERENCE, lambda ctx, inp, cfg: {"detections": [{"label": "car"}]})

    async def async_verify(ctx, inp, cfg):
        return {"verified": True, "detections": inp.get("detections", [])}

    executor.register_handler(NodeType.VERIFY, async_verify)

    results = await executor.execute(dag, {})
    assert results["sync_step"]["detections"][0]["label"] == "car"
    assert results["async_step"]["verified"] is True


@pytest.mark.asyncio
async def test_executor_sync_handler_still_works() -> None:
    dag = DAGDefinition(name="sync_test")
    dag.add_node(DAGNode(node_id="detect", node_type=NodeType.MODEL_INFERENCE))
    dag.entry_nodes = ["detect"]

    executor = DAGExecutor()
    executor.register_handler(NodeType.MODEL_INFERENCE, lambda ctx, inp, cfg: {"result": "ok"})

    results = await executor.execute(dag, {})
    assert results["detect"]["result"] == "ok"
```

- [ ] **Step 3: 运行新旧 DAG 测试确认通过**

```bash
uv run pytest tests/test_dag.py tests/test_executor_async.py -v
```
预期：全部通过

- [ ] **Step 4: 提交**

```bash
git add src/pipeline/executor.py tests/test_executor_async.py
git commit -m "fix(agent): async/sync handler dispatch in DAGExecutor"
```

---

### 任务 3: verify_handler 异步重写 + 缓存统一 + Worker handler 注册（WP1b/WP1c/WP4a）

**Files:**
- Modify: `src/pipeline/verify_handler.py`
- Modify: `tests/test_verify.py`
- Modify: `tests/test_verify_cache.py`
- Modify: `src/worker.py`

**Interfaces:**
- Consumes: `ResultCache` from `src.cache.result_cache`, `QwenVLClient` from `src.agent.client`
- Produces: async `verify_handler()` function

**Key decisions:**
- 将同步 verify_handler 改为纯 async 函数
- 删除自建同步 Redis 缓存，改用 `ResultCache`
- `asyncio.gather()` 并行化 LLM 验证调用
- Worker 补充 `AGGREGATE` + `CONDITION` handler 注册

- [ ] **Step 1: 重写 `verify_handler.py`**

```python
import base64
import logging
import asyncio
import time

import cv2
import numpy as np

logger = logging.getLogger(__name__)

_verify_client = None
_verify_cache = None
_verify_hasher = None


def _get_verify_client():
    global _verify_client
    if _verify_client is None:
        from src.agent.client import QwenVLClient
        _verify_client = QwenVLClient()
    return _verify_client


def _get_verify_hasher():
    global _verify_hasher
    if _verify_hasher is None:
        from src.cache.frame_hasher import FrameHasher
        _verify_hasher = FrameHasher()
    return _verify_hasher


async def _get_result_cache():
    global _verify_cache
    if _verify_cache is None:
        from src.core.config import settings
        if not settings.get("result_cache.enabled", True):
            return None
        from src.cache.result_cache import ResultCache
        from src.core.redis_client import get_redis
        redis = await get_redis()
        _verify_cache = ResultCache(redis)
    return _verify_cache


def _decode_frame(frame_b64: str):
    try:
        raw = base64.b64decode(frame_b64)
        arr = np.frombuffer(raw, dtype=np.uint8)
        return cv2.imdecode(arr, cv2.IMREAD_COLOR), raw
    except Exception:
        return None, None


async def _verify_one_detection(client, cache, frame, det, frame_hash, cache_key, camera_id):
    x1, y1, x2, y2 = det.get("bbox", [0, 0, 0, 0])
    x1, y1 = max(0, x1), max(0, y1)
    x2 = min(frame.shape[1], x2)
    y2 = min(frame.shape[0], y2)
    crop = frame[y1:y2, x1:x2]
    if crop.size == 0:
        det["verified"] = False
        det["verification_error"] = "empty_crop"
        return

    _, buf = cv2.imencode(".jpg", crop, [cv2.IMWRITE_JPEG_QUALITY, 85])
    crop_bytes = buf.tobytes()
    try:
        result = await client.verify(crop_bytes, det.get("label", ""), det.get("confidence", 0))
        det["verified"] = result.get("verified", False)
        if result.get("corrected_label"):
            det["corrected_label"] = result["corrected_label"]
        det["verification_reason"] = result.get("reason", "")
    except Exception as e:
        logger.warning("VERIFY call failed: %s", e)
        det["verified"] = False
        det["verification_error"] = str(e)
        return

    if cache:
        try:
            await cache.set(camera_id, frame_hash, {"verified": det["verified"], "reason": det.get("verification_reason", "")}, cache_key)
        except Exception:
            logger.debug("Cache store failed", exc_info=True)


async def verify_handler(context: dict, input_data: dict, node_config: dict) -> dict:
    threshold = node_config.get("verify_threshold", 0.5)
    margin = node_config.get("verify_margin", 0.3)
    upper = threshold + margin

    detections = input_data.get("detections", [])
    frame_b64 = context.get("frame", "")
    if not frame_b64 or not detections:
        return {"detections": detections, "verification_count": 0}

    frame, raw = _decode_frame(frame_b64)
    if frame is None:
        return {"detections": detections, "verification_count": 0, "error": "decode_failed"}

    client = _get_verify_client()
    cache = await _get_result_cache()
    hasher = _get_verify_hasher()
    frame_hash = hasher.compute(raw)
    camera_id = context.get("camera_id", "")

    tasks = []
    verified_detections = []
    v_count = 0

    for det in detections:
        conf = det.get("confidence", 0)
        if threshold <= conf < upper:
            cache_key = f"verify:{det.get('label', '')}"
            cached = None
            if cache:
                try:
                    cached = await cache.get(camera_id, frame_hash, cache_key)
                except Exception:
                    pass
            if cached:
                det["verified"] = cached.result.get("verified", False)
                det["verification_reason"] = cached.result.get("reason", "")
                det["verification_cache_hit"] = True
            else:
                tasks.append(_verify_one_detection(client, cache, frame, det, frame_hash, cache_key, camera_id))
            v_count += 1
        else:
            det["verified"] = True
        verified_detections.append(det)

    if tasks:
        await asyncio.gather(*tasks)

    return {
        "detections": verified_detections,
        "verification_count": v_count,
    }
```

- [ ] **Step 2: 修改 `tests/test_verify.py` async 化**

```python
import pytest
import numpy as np

from src.pipeline.verify_handler import verify_handler


def _make_frame(height=200, width=300):
    import cv2
    import base64
    img = np.zeros((height, width, 3), dtype=np.uint8)
    img[50:150, 100:200] = (255, 255, 255)
    _, buf = cv2.imencode(".jpg", img)
    return base64.b64encode(buf).decode("ascii")


@pytest.mark.asyncio
async def test_verify_no_candidates():
    dets = [
        {"bbox": [0, 0, 10, 10], "label": "car", "confidence": 0.95},
        {"bbox": [0, 0, 10, 10], "label": "bus", "confidence": 0.20},
    ]
    result = await verify_handler(
        {"frame": _make_frame()},
        {"detections": dets},
        {"verify_threshold": 0.5, "verify_margin": 0.3},
    )
    assert result["verification_count"] == 0
    assert all(d.get("verified") is True for d in result["detections"])


@pytest.mark.asyncio
async def test_verify_candidate_triggers_llm_call():
    import httpx
    from src.agent.client import QwenVLClient
    import src.pipeline.verify_handler as vh

    mock_transport = httpx.MockTransport(lambda req: httpx.Response(200, json={
        "choices": [{"message": {
            "content": '{"verified": true, "corrected_label": "person", "reason": "clearly visible"}',
            "role": "assistant",
        }}]
    }))
    _orig = vh._verify_client
    vh._verify_client = QwenVLClient(http_client=httpx.AsyncClient(transport=mock_transport))
    vh._verify_cache = None

    try:
        result = await verify_handler(
            {"frame": _make_frame()},
            {"detections": [{"bbox": [100, 50, 200, 150], "label": "person", "confidence": 0.65}]},
            {"verify_threshold": 0.5, "verify_margin": 0.3},
        )
        assert result["verification_count"] == 1
        d = result["detections"][0]
        assert d["verified"] is True
        assert d["verification_reason"] != ""
    finally:
        vh._verify_client = _orig
        vh._verify_cache = None


@pytest.mark.asyncio
async def test_verify_empty_frame():
    dets = [{"bbox": [100, 50, 200, 150], "label": "person", "confidence": 0.65}]
    result = await verify_handler(
        {"frame": ""},
        {"detections": dets},
        {},
    )
    assert result["verification_count"] == 0
    assert len(result["detections"]) == 1


@pytest.mark.asyncio
async def test_verify_no_detections():
    result = await verify_handler(
        {"frame": _make_frame()},
        {"detections": []},
        {},
    )
    assert result["verification_count"] == 0
    assert result["detections"] == []


@pytest.mark.asyncio
async def test_verify_edge_threshold():
    import httpx
    from src.agent.client import QwenVLClient
    import src.pipeline.verify_handler as vh

    mock_transport = httpx.MockTransport(lambda req: httpx.Response(200, json={
        "choices": [{"message": {
            "content": '{"verified": true, "corrected_label": "person", "reason": "ok"}',
            "role": "assistant",
        }}]
    }))
    _orig = vh._verify_client
    vh._verify_client = QwenVLClient(http_client=httpx.AsyncClient(transport=mock_transport))
    vh._verify_cache = None

    try:
        dets = [
            {"bbox": [100, 50, 200, 150], "label": "person", "confidence": 0.5},
            {"bbox": [100, 50, 200, 150], "label": "car", "confidence": 0.8},
            {"bbox": [100, 50, 200, 150], "label": "bus", "confidence": 0.79},
        ]
        result = await verify_handler(
            {"frame": _make_frame()},
            {"detections": dets},
            {"verify_threshold": 0.5, "verify_margin": 0.3},
        )
        assert result["verification_count"] == 2
    finally:
        vh._verify_client = _orig
        vh._verify_cache = None
```

- [ ] **Step 3: 修改 `tests/test_verify_cache.py` async 化**

```python
import pytest
import json
import time
from unittest.mock import MagicMock, AsyncMock
import numpy as np
import cv2
import base64

from src.pipeline.verify_handler import verify_handler


def _make_frame(height=200, width=300):
    img = np.zeros((height, width, 3), dtype=np.uint8)
    img[50:150, 100:200] = (255, 255, 255)
    _, buf = cv2.imencode(".jpg", img)
    return base64.b64encode(buf).decode("ascii")


class FakeCacheResult:
    def __init__(self, result, context_hash):
        self.result = result
        self.context_hash = context_hash
        self.created_at = time.time()


@pytest.mark.asyncio
async def test_verify_cache_hit_skips_llm():
    import src.pipeline.verify_handler as vh

    mock_cache = AsyncMock()
    mock_cache.get.return_value = FakeCacheResult(
        result={"verified": True, "reason": "cached_result"},
        context_hash="verify:person",
    )
    vh._verify_cache = mock_cache

    _orig_client = vh._verify_client
    vh._verify_client = MagicMock()

    try:
        result = await verify_handler(
            {"frame": _make_frame(), "camera_id": "cam-1"},
            {"detections": [{"bbox": [100, 50, 200, 150], "label": "person", "confidence": 0.65}]},
            {"verify_threshold": 0.5, "verify_margin": 0.3},
        )
        d = result["detections"][0]
        assert d.get("verification_cache_hit"), "should have cache_hit flag"
        assert d["verified"] is True
        assert d["verification_reason"] == "cached_result"
        vh._verify_client.verify.assert_not_called()
    finally:
        vh._verify_client = _orig_client
        vh._verify_cache = None


@pytest.mark.asyncio
async def test_verify_cache_miss_calls_llm():
    import httpx
    from src.agent.client import QwenVLClient
    import src.pipeline.verify_handler as vh

    mock_cache = AsyncMock()
    mock_cache.get.return_value = None
    vh._verify_cache = mock_cache

    mock_transport = httpx.MockTransport(lambda req: httpx.Response(200, json={
        "choices": [{"message": {
            "content": '{"verified": true, "reason": "llm_result"}',
            "role": "assistant",
        }}]
    }))
    _orig = vh._verify_client
    vh._verify_client = QwenVLClient(http_client=httpx.AsyncClient(transport=mock_transport))

    try:
        result = await verify_handler(
            {"frame": _make_frame(), "camera_id": "cam-1"},
            {"detections": [{"bbox": [100, 50, 200, 150], "label": "person", "confidence": 0.65}]},
            {"verify_threshold": 0.5, "verify_margin": 0.3},
        )
        assert result["verification_count"] == 1
        d = result["detections"][0]
        assert d["verification_reason"] == "llm_result"
        assert mock_cache.set.called, "should store result in cache"
    finally:
        vh._verify_client = _orig
        vh._verify_cache = None
```

- [ ] **Step 4: 修改 `worker.py` 补充 handler 注册**

在 `_init_fast_path()` 方法中（132-137 行）：

```python
def _init_fast_path() -> tuple[SceneRouter, PipelineRegistry, DAGExecutor, FastPathHandler]:
    router = SceneRouter()
    registry = PipelineRegistry()
    executor = DAGExecutor()
    executor.register_handler(NodeType.MODEL_INFERENCE, _inference_handler)
    executor.register_handler(NodeType.VERIFY, verify_handler)
    executor.register_handler(NodeType.AGGREGATE, aggregate_handler)
    executor.register_handler(NodeType.CONDITION, condition_handler)
    _register_default_pipelines(registry)
    handler = FastPathHandler(router, registry, executor)
    return router, registry, executor, handler
```

并添加 import（第 21-22 行区域）：

```python
from src.pipeline.aggregate_handler import aggregate_handler
from src.pipeline.condition_handler import condition_handler
```

- [ ] **Step 5: 运行验证测试**

```bash
uv run pytest tests/test_verify.py tests/test_verify_cache.py tests/test_dag.py tests/test_executor_async.py -v
```
预期：全部通过

- [ ] **Step 6: 提交**

```bash
git add src/pipeline/verify_handler.py tests/test_verify.py tests/test_verify_cache.py src/worker.py
git commit -m "fix(agent): async verify_handler + unified ResultCache + worker handler registration"
```

---

### 任务 4: Orchestrator 双路径消除 + Tool 管线 + HTTP 客户端生命周期（WP1d/WP1e/WP1f）

**Files:**
- Modify: `src/agent/orchestrator.py`
- Modify: `src/agent/tools.py`
- Modify: `src/agent/client.py`

**Interfaces:**
- Consumes: `FastPathHandler`, `CVAgent`, `InferenceOrchestrator` (unchanged)
- Produces: `AgentOrchestrator.process()` 不再重复调用 fast_path

- [ ] **Step 1: 修改 `orchestrator.py` — 消除双重 fast path**

```python
class AgentOrchestrator:
    def __init__(
        self,
        fast_path: FastPathHandler,
        agent: CVAgent,
        inference: InferenceOrchestrator,
    ):
        self.fast_path = fast_path
        self.agent = agent
        self.inference = inference

    async def process(
        self,
        frame_context: dict[str, Any],
        image_data: bytes | None = None,
    ) -> dict[str, Any]:
        if image_data:
            return await self.agent.analyze_with_image(frame_context, image_data)
        return await self.agent.analyze(frame_context)
```

- [ ] **Step 2: 修改 `tools.py` — base64 → numpy 管线**

在 `execute_tool` 方法中添加解码逻辑：

```python
async def execute_tool(self, name: str, arguments: dict[str, Any]) -> Any:
    tool = self._tools.get(name)
    if tool is None:
        raise ValueError(f"Unknown tool: {name}")

    model_id = tool.get("model_id")
    if model_id:
        import base64
        import cv2
        import numpy as np

        image_b64 = arguments.get("image", "")
        if image_b64:
            try:
                raw = base64.b64decode(image_b64)
                arr = np.frombuffer(raw, dtype=np.uint8)
                arguments["image"] = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            except Exception as e:
                logger.warning("Failed to decode image in tool %s: %s", name, e)

        result = await self.orchestrator.infer(model_id, arguments)
        return result["output"]

    logger.warning("Tool %s has no model_id, returning stub", name)
    return {"stub": True}
```

- [ ] **Step 3: 修改 `client.py` — 添加 `aclose()` 方法**

```python
class QwenVLClient(LLMClient):
    # ... existing __init__ stays the same

    async def aclose(self) -> None:
        await self._http.aclose()
```

在 `__init__` 中添加 `self._owned_http = http_client is None`：

```python
def __init__(self, ..., http_client: httpx.AsyncClient | None = None):
    ...
    self._http = http_client or httpx.AsyncClient(timeout=httpx.Timeout(timeout))
    self._owned_http = http_client is None
```

- [ ] **Step 4: 提交**

```bash
git add src/agent/orchestrator.py src/agent/tools.py src/agent/client.py
git commit -m "fix(agent): remove double fast path, base64->numpy tool pipeline, http client lifecycle"
```

---

### 任务 5: DI 重构 — deps.py + shared_init.py + 路由迁移（WP3）

**Files:**
- Create: `src/api/deps.py`
- Create: `src/pipeline/shared_init.py`
- Modify: `src/api/routes/analyze.py`
- Modify: `src/api/routes/tasks.py`
- Modify: `src/api/routes/alerts.py`
- Modify: `src/api/routes/admin_rules.py`
- Modify: `src/pipeline/condition_handler.py`
- Modify: `src/api/app.py`
- Modify: `src/worker.py`

**Interfaces:**
- Consumes: `async_sessionmaker` from `sqlalchemy.ext.asyncio`
- Produces: `get_db()` async iterator for FastAPI `Depends()`, `register_default_pipelines()` and `register_dag_handlers()` for shared init

- [ ] **Step 1: 新建 `src/api/deps.py`**

```python
from collections.abc import AsyncIterator
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

_session_factory: async_sessionmaker[AsyncSession] | None = None


def init_session_factory(factory: async_sessionmaker[AsyncSession]) -> None:
    global _session_factory
    _session_factory = factory


async def get_db() -> AsyncIterator[AsyncSession]:
    if _session_factory is None:
        raise RuntimeError("Database session factory not initialized")
    async with _session_factory() as session:
        yield session
```

- [ ] **Step 2: 新建 `src/pipeline/shared_init.py`**

```python
import logging

from src.pipeline.registry import PipelineRegistry
from src.pipeline.executor import DAGExecutor
from src.pipeline.dag import DAGDefinition, DAGNode, NodeType

logger = logging.getLogger(__name__)


def register_default_pipelines(registry: PipelineRegistry) -> None:
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


def register_dag_handlers(executor: DAGExecutor) -> None:
    from src.pipeline.verify_handler import verify_handler
    from src.pipeline.aggregate_handler import aggregate_handler
    from src.pipeline.condition_handler import condition_handler

    executor.register_handler(NodeType.AGGREGATE, aggregate_handler)
    executor.register_handler(NodeType.CONDITION, condition_handler)
```

- [ ] **Step 3: 修改 `analyze.py` — 迁移到 Depends(get_db)**

删除模块级 `_db_session_factory`（第 20 行）和 `init_db_session_factory()`（第 29-31 行）。

`analyze_frame` 路由中的 DB 访问改为使用 `Depends(get_db)`。但注意 `analyze_frame` 当前不是 FastAPI 依赖注入的路由参数 — 它是 `post` 路由。对于同步模式下的 `reject` 和 `skip` 中的 DB 操作，将 session 作为路由参数注入。

- [ ] **Step 3a: 删除 `_db_session_factory` 和 `init_db_session_factory`**

```python
# 删除这些行
_db_session_factory = None  # 第 20 行

def init_db_session_factory(factory) -> None:  # 第 29-31 行
    global _db_session_factory
    _db_session_factory = factory
```

- [ ] **Step 3b: 在 analyze_frame 路由中注入 session**

修改 `analyze.py` 的 `analyze_frame` 路由，注入 `session` 参数替代 `_db_session_factory`：

```python
@router.post("/frame")
async def analyze_frame(
    body: dict,
    session: AsyncSession = Depends(get_db),
    sync: bool = Query(False, description="同步模式（调试用）"),
) -> dict:
    if _queue is None:
        raise HTTPException(500, "Queue not initialized")

    frame_raw = body.get("frame", "")
    if len(frame_raw) > MAX_FRAME_BYTES:
        raise HTTPException(413, "Frame too large (max 10MB)")

    if sync:
        orchestrator = getattr(analyze_frame, "_orchestrator", None)
        if orchestrator is None:
            raise HTTPException(500, "Orchestrator not initialized in sync mode")
        body["frame"] = frame_raw
        result = await orchestrator.process(body)
        return result

    task_id = str(uuid.uuid4())
    camera_id = body.get("camera_id", "unknown")

    if _preprocessor is not None:
        image = _decode_frame(frame_raw)
        if image is not None:
            decision = _preprocessor.process(image, camera_id)

            if decision.action == "reject":
                task = Task(
                    id=task_id, camera_id=camera_id, path_taken="rejected",
                    status="rejected", rejection_reason=decision.rejection_reason, alert_count=1,
                )
                session.add(task)
                alert = Alert(
                    task_id=task_id, alert_type="quality_rejected",
                    label=decision.rejection_reason or "unknown",
                    bbox=None, confidence=0.0, verified_by="model", status="pending",
                )
                session.add(alert)
                await session.commit()
                logger.info("Frame %s rejected: %s", task_id, decision.rejection_reason)
                return {"task_id": task_id, "status": "rejected", "reason": decision.rejection_reason}

            if decision.action == "skip":
                task = Task(
                    id=task_id, camera_id=camera_id, path_taken="skipped",
                    status="skipped", rejection_reason=decision.rejection_reason,
                )
                session.add(task)
                await session.commit()
                logger.debug("Frame %s skipped by sampler", task_id)
                return {"task_id": task_id, "status": "skipped", "reason": decision.rejection_reason}
    ...
```

- [ ] **Step 4: 修改 `tasks.py` — 迁移到 Depends(get_db)**

```python
from src.api.deps import get_db

# 删除 _db_session_factory 和 init_db_session_factory

@router.get("")
async def list_tasks(
    status: str | None = Query(None, description="Filter by status"),
    camera_id: str | None = Query(None, description="Filter by camera_id"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_db),
) -> dict:
    ...
    # 使用 session 替代 _db_session_factory()


@router.get("/{task_id}/results")
async def get_task_result(
    task_id: str,
    session: AsyncSession = Depends(get_db),
) -> dict:
    ...
```

- [ ] **Step 5: 修改 `alerts.py` — 迁移到 Depends(get_db)**

```python
from src.api.deps import get_db

# 删除 _db_session_factory 和 init_db_session_factory

@router.get("")
async def list_alerts(
    ...,
    session: AsyncSession = Depends(get_db),
) -> dict:
    ...

@router.get("/{alert_id}")
async def get_alert(
    alert_id: int,
    session: AsyncSession = Depends(get_db),
) -> dict:
    ...
```

- [ ] **Step 6: 修改 `admin_rules.py` — 迁移到 Depends(get_db)**

```python
from src.api.deps import get_db

# 删除 _db_session_factory 和 init_db_session_factory

# 所有路由添加 session 参数
@rules_router.post("")
async def create_rule(body: RuleCreate, session: AsyncSession = Depends(get_db)) -> dict:
    ...
```

- [ ] **Step 7: 修改 `condition_handler.py` — 接受 session 参数**

将 `condition_handler` 改为接受 `session` 参数（通过 DAG context 传入）：

```python
async def condition_handler(context: dict, input_data: dict, node_config: dict) -> dict:
    rule_refs: list[int] = node_config.get("rule_refs", [])
    camera_id = context.get("camera_id", "")
    scene_type = context.get("scene_type", "")
    task_id = context.get("task_id", "")
    session = context.get("db_session")

    if not rule_refs:
        return {"condition_results": [], "triggered": False}

    if session is None:
        logger.error("condition_handler: no db_session in context")
        return {"condition_results": [], "triggered": False}

    # 直接使用 session 参数，不再导入 _session_factory
    ...
```

- [ ] **Step 8: 修改 `app.py` — 使用 deps + shared_init**

在 lifespan 中：

```python
from src.api.deps import init_session_factory, get_db
from src.pipeline.shared_init import register_default_pipelines, register_dag_handlers

async def lifespan(app: FastAPI):
    from src.core.database import init_db
    from sqlalchemy.ext.asyncio import async_sessionmaker
    db_url = os.getenv("DATABASE_URL") or settings.get("database.url") or "sqlite+aiosqlite:///data/aimp.db"
    db_engine = await init_db(db_url)
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    init_session_factory(session_factory)
    # 删除所有模块级别的 init_db_session_factory 调用
    _init_components()
    ...
```

在 `_init_components()` 中：

```python
def _init_components() -> None:
    ...
    executor.register_handler(NodeType.MODEL_INFERENCE, _inference_handler)
    executor.register_handler(NodeType.VERIFY, verify_handler)
    register_dag_handlers(executor)
    register_default_pipelines(pipeline_registry)
    ...
```

- [ ] **Step 9: 修改 `worker.py` — 使用 shared_init**

```python
from src.pipeline.shared_init import register_default_pipelines, register_dag_handlers

def _init_fast_path() -> tuple[SceneRouter, PipelineRegistry, DAGExecutor, FastPathHandler]:
    router = SceneRouter()
    registry = PipelineRegistry()
    executor = DAGExecutor()
    executor.register_handler(NodeType.MODEL_INFERENCE, _inference_handler)
    executor.register_handler(NodeType.VERIFY, verify_handler)
    register_dag_handlers(executor)
    register_default_pipelines(registry)
    handler = FastPathHandler(router, registry, executor)
    return router, registry, executor, handler
```

并删除 `worker.py` 中的 `_register_default_pipelines` 局部函数（143-155 行）。

- [ ] **Step 10: 运行测试确认无回归**

```bash
uv run pytest tests/ -v -x
```
预期：全部通过（注意：`test_config_manager.py` 已删除，所以少 6 个测试）

- [ ] **Step 11: 提交**

```bash
git add src/api/deps.py src/pipeline/shared_init.py src/api/routes/analyze.py src/api/routes/tasks.py src/api/routes/alerts.py src/api/routes/admin_rules.py src/pipeline/condition_handler.py src/api/app.py src/worker.py
git commit -m "refactor(core): DI refactoring with Depends(get_db) and shared_init"
```

---

### 任务 6: Redis 客户端重试 + 优雅降级（WP4b）

**Files:**
- Modify: `src/core/redis_client.py`

- [ ] **Step 1: 修改 `redis_client.py`**

```python
import logging
import asyncio

import redis.asyncio as aioredis

from src.core.config import settings

logger = logging.getLogger(__name__)

_redis: aioredis.Redis | None = None
_RETRY_DELAYS = [0.5, 1.0, 2.0]


async def get_redis() -> aioredis.Redis | None:
    global _redis
    if _redis is not None:
        return _redis
    redis_url = settings.get("queue.redis_url", "redis://localhost:6379/0")
    last_error = None
    for attempt, delay in enumerate(_RETRY_DELAYS + [0]):
        try:
            _redis = await aioredis.from_url(redis_url, socket_connect_timeout=2)
            await _redis.ping()
            logger.info("shared Redis client connected to %s", redis_url)
            return _redis
        except Exception as e:
            last_error = e
            if attempt < len(_RETRY_DELAYS):
                logger.warning("Redis connection attempt %d failed: %s, retrying in %.1fs", attempt + 1, e, delay)
                await asyncio.sleep(delay)
    logger.error("Redis connection failed after %d attempts: %s", len(_RETRY_DELAYS) + 1, last_error)
    return None


async def close_redis() -> None:
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None


async def ping() -> bool:
    try:
        r = await get_redis()
        if r is None:
            return False
        return await r.ping()
    except Exception:
        return False
```

注意: `get_redis()` 返回类型从 `aioredis.Redis` 改为 `aioredis.Redis | None`。调用者需要处理 None 情况。

- [ ] **Step 2: 处理 `ResultCache` 中 Redis 为 None 的情况**

修改 `src/cache/result_cache.py`，在 Redis 为 None 时 `get()` 返回 None，`set()` 不执行：

```python
async def get(self, camera_id, frame_hash, context_hash=""):
    if self.redis is None:
        return None
    ...

async def set(self, camera_id, frame_hash, result, context_hash=""):
    if self.redis is None:
        return
    ...
```

- [ ] **Step 3: 提交**

```bash
git add src/core/redis_client.py src/cache/result_cache.py
git commit -m "fix(core): Redis client retry with backoff + graceful None handling"
```

---

### 任务 7: 资源管理 — 视频缓冲压缩 + 推理会话 LRU（WP5）

**Files:**
- Modify: `src/ingestion/video_cache.py`
- Modify: `src/models/inference.py`

**Key decisions:**
- `CachedFrame.data` 从 `np.ndarray` 改为 `bytes`（JPEG 编码）
- 所有读帧处自动解码（get_segment 等方法返回解码后的 ndarray）
- InferenceOrchestrator 新增 LRU 上限（默认 max_concurrent=5）

- [ ] **Step 1: 修改 `video_cache.py` — JPEG 压缩存储**

```python
import base64
import cv2
import numpy as np

@dataclass
class CachedFrame:
    data: bytes           # JPEG 编码的帧数据
    timestamp: float
    task_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    _decoded: np.ndarray | None = field(default=None, repr=False)

    def memory_bytes(self) -> int:
        return sys.getsizeof(self.data) + sys.getsizeof(self.metadata)

    def decode(self) -> np.ndarray:
        if self._decoded is not None:
            return self._decoded
        arr = np.frombuffer(self.data, dtype=np.uint8)
        self._decoded = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        return self._decoded
```

修改 `push()` 方法进行压缩：

```python
def push(self, camera_id: str, frame: np.ndarray, task_id: str = "", metadata: dict | None = None) -> None:
    if camera_id not in self._buffers:
        self._buffers[camera_id] = deque()
    now = time.time()
    _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
    cf = CachedFrame(data=buf.tobytes(), timestamp=now, task_id=task_id, metadata=metadata or {})
    self._buffers[camera_id].append(cf)
    self._trim(camera_id)
    self._enforce_memory_limit()
```

`get_segment()` 返回解码后的帧：

```python
def get_segment(self, camera_id: str, start: float, end: float) -> list[CachedFrame]:
    buf = self._buffers.get(camera_id)
    if not buf:
        return []
    return [f for f in buf if start <= f.timestamp <= end]
```
（调用方使用 `cf.decode()` 获取 numpy array）

- [ ] **Step 2: 修改 `inference.py` — LRU 会话上限**

```python
from collections import OrderedDict

class InferenceOrchestrator:
    def __init__(self, model_registry: ModelRegistry, max_concurrent: int = 5) -> None:
        self.model_registry = model_registry
        self._executor = DAGExecutor()
        self._adapters: dict[str, ModelAdapter] = {}
        self._max_concurrent = max_concurrent
        self._active_sessions: OrderedDict[str, float] = OrderedDict()

    def _acquire_session(self, model_id: str) -> bool:
        now = time.monotonic()
        self._active_sessions[model_id] = now
        self._active_sessions.move_to_end(model_id)
        if len(self._active_sessions) > self._max_concurrent:
            oldest = next(iter(self._active_sessions))
            del self._active_sessions[oldest]
            logger.warning("LRU evicting oldest session: %s", oldest)
        return True

    async def infer(self, model_id: str, input_data: Any) -> dict[str, Any]:
        self._acquire_session(model_id)
        spec = self.model_registry.get(model_id)
        ...
```

- [ ] **Step 3: 提交**

```bash
git add src/ingestion/video_cache.py src/models/inference.py
git commit -m "perf(core): JPEG compressed video buffer + inference LRU session cap"
```

---

### 任务 8: API 路由前缀规范化 + 限流器 Redis 后端（WP6a/WP6c）

**Files:**
- Modify: `src/api/routes/health.py`
- Modify: `src/api/routes/ws.py`
- Modify: `src/api/routes/ingest.py`
- Modify: `src/api/routes/models.py`
- Modify: `src/api/routes/routing.py`
- Modify: `src/api/routes/video_cache.py`
- Modify: `src/api/routes/api_keys.py`
- Modify: `src/api/routes/config_routes.py`
- Modify: `src/api/routes/analyze.py`
- Modify: `src/core/security.py`
- Modify: `src/api/app.py`

**Key decisions:**
- 所有业务路由前缀统一为 `/api/v1/`
- health 从 `/health` → `/api/v1/health`
- ws 从 `/ws` → `/api/v1/ws`
- security.py 中的路径前缀常量同步更新
- RateLimiter 在有 Redis 时使用 Redis（原子计数器），否则回退 TokenBucket

- [ ] **Step 1: 统一各路由模块的前缀**

| 文件 | 旧前缀 | 新前缀 |
|------|--------|--------|
| `health.py` | (无) 路径 `/health` | `/api/v1/health` |
| `ws.py` | 路径 `/ws` | `/api/v1/ws` |
| `ingest.py` | `/v1` | `/api/v1` |
| `models.py` | `/v1/models` | `/api/v1/models` |
| `routing.py` | `/v1/routing` | `/api/v1/routing` |
| `video_cache.py` | `/v1/video-cache` | `/api/v1/video-cache` |
| `api_keys.py` | `/v1/admin/api-keys` | `/api/v1/admin/api-keys` |
| `config_routes.py` | `/v1/config` | `/api/v1/config` |
| `analyze.py` | `/v1/analyze` | `/api/v1/analyze` |
| `tasks.py` | `/v1/tasks` | `/api/v1/tasks` |
| `alerts.py` | `/v1/alerts` | `/api/v1/alerts` |
| `admin_rules.py` | (已经是 `/api/v1/admin/...`) | 不变 |

示例修改 `health.py`:

```python
router = APIRouter(prefix="/api/v1/health", tags=["health"])

@router.get("")
async def health() -> dict:
    return {"status": "ok", "service": "aimiddleplatform", "version": "0.1.0"}
```

示例修改 `ws.py`:

```python
router = APIRouter(prefix="/api/v1/ws", tags=["websocket"])

@router.websocket("")
async def websocket_endpoint(...):
    ...
```

- [ ] **Step 2: 同步 `security.py` 中的路径前缀常量**

```python
BUSINESS_PREFIXES = (
    "/api/v1/analyze", "/api/v1/tasks", "/api/v1/alerts",
    "/api/v1/video-cache", "/api/v1/models", "/api/v1/routing",
    "/api/v1/config",
)
ADMIN_PREFIXES = ("/api/v1/admin", "/api/v1/auth", "/api/v1/system")
EXEMPT_PATHS = {
    "/api/v1/auth/login", "/api/v1/auth/refresh",
    "/api/v1/analyze/ping", "/api/v1/health",
    "/metrics",
}
```

- [ ] **Step 3: `app.py` — 调用 `app.include_router` 时不需要 prefix 参数**

所有路由的 prefix 已经定义在各自 router 中，`include_router` 调用不变。

添加 health router 的 include：

```python
app.include_router(health_router)  # 已有，prefix 已在 router 中
```

删除旧的 `/health` 和 `/metrics` 特殊路由（如果存在）。

- [ ] **Step 4: 修改 `security.py` — Redis 后端限流**

```python
class RateLimiter:
    def __init__(self) -> None:
        self._buckets: dict[str, TokenBucket] = {}
        self._redis = None

    async def _get_redis(self):
        if self._redis is None:
            from src.core.redis_client import get_redis
            self._redis = await get_redis()
        return self._redis

    async def check(self, key: str, rate_per_second: float = 10, tokens: int = 1) -> tuple[bool, int]:
        redis = await self._get_redis()
        if redis is not None:
            return await self._check_redis(redis, key, rate_per_second, tokens)
        return self._check_local(key, rate_per_second, tokens)

    async def _check_redis(self, redis, key: str, rate: float, tokens: int) -> tuple[bool, int]:
        now = int(time.time())
        window_key = f"ratelimit:{key}:{now}"
        count = await redis.get(window_key)
        if count is None:
            await redis.setex(window_key, 1, tokens)
            return True, int(rate) - tokens
        count = int(count)
        if count >= rate:
            return False, 0
        await redis.incr(window_key)
        return True, int(rate) - count

    def _check_local(self, key: str, rate_per_second: float, tokens: int) -> tuple[bool, int]:
        if key not in self._buckets or self._buckets[key].rate != rate_per_second:
            self._buckets[key] = TokenBucket(rate_per_second)
        allowed = self._buckets[key].consume(tokens)
        remaining = int(self._buckets[key].remaining())
        return allowed, remaining
```

注意: `check()` 转为 `async`。所有调用 `limiter.check()` 的地方需要加 `await`。在 `app.py` 的 `auth_middleware` 中：

```python
limiter = get_rate_limiter()
allowed, remaining = await limiter.check(api_key, info["rate_per_second"])
```

- [ ] **Step 5: 更新 nginx 配置**

单条 location 规则：

```nginx
location /api/v1/ {
    proxy_pass http://aimp-api:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}

location / {
    root /usr/share/nginx/html;
    index index.html;
    try_files $uri $uri/ /index.html;
}
```

- [ ] **Step 6: 提交**

```bash
git add src/api/routes/health.py src/api/routes/ws.py src/api/routes/ingest.py src/api/routes/models.py src/api/routes/routing.py src/api/routes/video_cache.py src/api/routes/api_keys.py src/api/routes/config_routes.py src/api/routes/analyze.py src/api/routes/tasks.py src/api/routes/alerts.py src/core/security.py src/api/app.py deploy/nginx.conf
git commit -m "refactor(api): unified /api/v1/ prefix + Redis-backed rate limiter"
```

---

## 最终验证

所有任务完成后，执行最终回归测试：

```bash
uv run pytest tests/ -v
uv run pytest tests/ --timeout=30
```

预期：全部 300+ 测试通过（`test_config_manager.py` 已删除所以少 6 个，新增 `test_executor_async.py` 3 个，`test_config.py` 4 个，总数与原数一致）
