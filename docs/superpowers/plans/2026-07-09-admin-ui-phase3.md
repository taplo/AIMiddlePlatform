# Phase 3: Pipeline Orchestration + Logs & Tracing Implementation Plan

> **For agentic workers:** Subagent-driven approach recommended. Tasks 1-6 (backend) can run sequentially; tasks 7-10 (frontend) depend on 1-6.

**Goal:** Add pipeline (DAG) orchestration management and structured logs/tracing views to the admin UI.

**Architecture:** Backend stores DAG definitions in-memory via existing PipelineRegistry + adds in-memory log/trace ring buffers (captured by custom logging handler and OpenTelemetry span processor). Frontend adds 3 new admin pages: Pipelines (with visual DAG editor), Logs (filterable table), Traces (list + detail drill-down).

**Tech Stack:** FastAPI, Vue 3 + Element Plus, canvas-based DAG editor (native canvas, no heavy dependencies), OpenTelemetry SDK, logging.

**Plan location:** `docs/superpowers/plans/2026-07-09-admin-ui-phase3.md`

---
## File Structure

### Backend — new files
| File | Responsibility |
|---|---|
| `src/api/routes/admin/pipelines.py` | Pipeline CRUD + DAG get/set endpoints |
| `src/monitoring/log_buffer.py` | Ring buffer `LogBuffer` storing JSON log entries; `BufferLogHandler` |
| `src/monitoring/trace_store.py` | In-memory `TraceStore` collecting spans; custom `BatchSpanProcessor` variant |
| `tests/test_admin_pipelines.py` | Test pipeline CRUD endpoints |
| `tests/test_log_buffer.py` | Test LogBuffer + BufferLogHandler |
| `tests/test_trace_store.py` | Test TraceStore |

### Backend — modified files
| File | Change |
|---|---|
| `src/api/app.py` | Register new routers; init log buffer and trace store in lifespan |
| `src/monitoring/__init__.py` | Export new symbols |

### Frontend — new files
| File | Responsibility |
|---|---|
| `frontend/src/api/pipelines.ts` | Pipeline API client |
| `frontend/src/api/logs.ts` | Log query API client |
| `frontend/src/api/traces.ts` | Trace query API client |
| `frontend/src/stores/pipelines.ts` | Pipeline Pinia store |
| `frontend/src/stores/logs.ts` | Logs Pinia store |
| `frontend/src/stores/traces.ts` | Traces Pinia store |
| `frontend/src/views/Pipelines/Index.vue` | Pipeline list + DAG editor |
| `frontend/src/views/Logs/Index.vue` | Log viewer with filters |
| `frontend/src/views/Traces/Index.vue` | Trace list page |
| `frontend/src/views/Traces/Detail.vue` | Trace detail with span waterfall |

### Frontend — modified files
| File | Change |
|---|---|
| `frontend/src/router/index.ts` | Add Pipeline, Logs, Trace routes |
| `frontend/src/components/Sidebar.vue` | Add navigation links |

---
## Tasks

### Task 1: LogBuffer — in-memory ring buffer for structured logs

**Files:**
- Create: `src/monitoring/log_buffer.py`
- Test: `tests/test_log_buffer.py`

**Interfaces:**
- Consumes: `logging.Handler`, `json`
- Produces: `LogBuffer` class, `buffer_handler` singleton, `init_log_buffer()` function, `get_logs()`, `clear_logs()`

- [ ] **Step 1: Write tests**

```python
# tests/test_log_buffer.py
import logging
from src.monitoring.log_buffer import LogBuffer, init_log_buffer, get_logs, clear_logs


def test_log_buffer_maxlen():
    buf = LogBuffer(maxlen=10, level=logging.INFO)
    for i in range(15):
        buf.info("msg %d", i)
    assert len(buf.get_all()) == 10
    assert buf.get_all()[-1]["message"] == "msg 14"


def test_log_buffer_level_filter():
    buf = LogBuffer(maxlen=50, level=logging.WARNING)
    buf.info("should not appear")
    buf.warning("warning msg")
    buf.error("error msg")
    entries = buf.get_all()
    assert len(entries) == 2
    assert entries[0]["level"] == "WARNING"
    assert entries[1]["level"] == "ERROR"


def test_get_logs_empty():
    clear_logs()
    assert get_logs() == {"logs": [], "total": 0}


def test_get_logs_filter_level():
    clear_logs()
    init_log_buffer(maxlen=100)
    logger = logging.getLogger("test_logs")
    logger.warning("warn 1")
    logger.error("err 1")
    logger.info("info 1")
    logger.warning("warn 2")
    result = get_logs(level="WARNING")
    assert result["total"] == 2
    assert all(e["level"] == "WARNING" for e in result["logs"])


def test_get_logs_filter_module():
    clear_logs()
    init_log_buffer(maxlen=100)
    logging.getLogger("mod_a").info("from a")
    logging.getLogger("mod_b").info("from b")
    result = get_logs(module="mod_a")
    assert result["total"] == 1
    assert result["logs"][0]["logger"] == "mod_a"


def test_get_logs_search():
    clear_logs()
    init_log_buffer(maxlen=100)
    logging.getLogger("test").warning("connection timeout to db")
    logging.getLogger("test").info("request succeeded")
    result = get_logs(q="timeout")
    assert result["total"] == 1
    assert "timeout" in result["logs"][0]["message"]
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
uv run python -m pytest tests/test_log_buffer.py -v
```
Expected: ModuleNotFoundError or ImportError for `src.monitoring.log_buffer`

- [ ] **Step 3: Implement LogBuffer + init/get/clear**

```python
# src/monitoring/log_buffer.py
import logging
import threading
from collections import deque
from datetime import datetime, timezone
from typing import Any

_buffer: deque[dict[str, Any]] | None = None
_lock = threading.Lock()
_maxlen = 1000


class LogBuffer(logging.Handler):
    def __init__(self, maxlen: int = 1000, level: int = logging.INFO):
        super().__init__(level=level)
        self.maxlen = maxlen
        self.buffer = deque(maxlen=maxlen)

    def emit(self, record: logging.LogRecord) -> None:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "func": record.funcName,
            "line": record.lineno,
        }
        if record.exc_info and record.exc_info[0]:
            entry["exception"] = self.formatException(record.exc_info)
        self.buffer.append(entry)

    def get_all(self) -> list[dict[str, Any]]:
        return list(self.buffer)


def init_log_buffer(maxlen: int = 1000, level: int = logging.INFO) -> None:
    global _buffer, _maxlen
    handler = LogBuffer(maxlen=maxlen, level=level)
    handler.setFormatter(logging.Formatter())
    root = logging.getLogger()
    root.addHandler(handler)
    _maxlen = maxlen
    _buffer = handler.buffer


def get_logs(
    level: str | None = None,
    module: str | None = None,
    q: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    global _buffer
    if _buffer is None:
        return {"logs": [], "total": 0}
    with _lock:
        entries = list(_buffer)
    if level:
        entries = [e for e in entries if e["level"] == level.upper()]
    if module:
        entries = [e for e in entries if module.lower() in e["logger"].lower()]
    if q:
        ql = q.lower()
        entries = [e for e in entries if ql in e["message"].lower()]
    entries.reverse()
    total = len(entries)
    sliced = entries[offset : offset + limit]
    return {"logs": sliced, "total": total}


def clear_logs() -> None:
    global _buffer
    with _lock:
        if _buffer is not None:
            _buffer.clear()
```

- [ ] **Step 4: Run tests**

Run:
```bash
uv run python -m pytest tests/test_log_buffer.py -v
```
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add src/monitoring/log_buffer.py tests/test_log_buffer.py
git commit -m "feat: add LogBuffer in-memory ring buffer for structured logs"
```

---
### Task 2: TraceStore — in-memory span storage

**Files:**
- Create: `src/monitoring/trace_store.py`
- Test: `tests/test_trace_store.py`

**Interfaces:**
- Consumes: `opentelemetry.sdk.trace.export.SpanExporter`, `opentelemetry.sdk.trace.ReadableSpan`
- Produces: `TraceStore` class, `init_trace_store()`, `get_traces()`, `get_trace_detail()` functions

- [ ] **Step 1: Write tests**

```python
# tests/test_trace_store.py
import time
from src.monitoring.trace_store import TraceStore, init_trace_store, get_traces, get_trace_detail


def test_trace_store_store_and_retrieve():
    store = TraceStore(maxlen=50)
    store.export([_make_span("trace1", "span1", "operation1", 0.1, True)])
    traces = store.get_traces()
    assert len(traces) >= 1
    assert traces[0]["trace_id"] == "trace1"


def test_trace_store_error_filter():
    store = TraceStore(maxlen=50)
    store.export([_make_span("t1", "s1", "op1", 0.1, True)])
    store.export([_make_span("t2", "s2", "op2", 0.1, False)])
    err_traces = store.get_traces(error_only=True)
    assert len(err_traces) == 1
    assert err_traces[0]["trace_id"] == "t2"


def test_trace_store_min_duration():
    store = TraceStore(maxlen=50)
    store.export([_make_span("t1", "s1", "op1", 0.05, True)])
    store.export([_make_span("t2", "s2", "op2", 0.2, True)])
    filtered = store.get_traces(min_duration_ms=100)
    assert len(filtered) == 1
    assert filtered[0]["trace_id"] == "t2"


def test_get_trace_detail():
    store = TraceStore(maxlen=50)
    spans = [
        _make_span("trace_x", "root", "root_op", 0.5, True),
        _make_span("trace_x", "child", "child_op", 0.3, True),
    ]
    for s in spans:
        store.export([s])
    detail = store.get_trace_detail("trace_x")
    assert detail is not None
    assert detail["trace_id"] == "trace_x"
    assert len(detail["spans"]) == 2


def _make_span(trace_id: str, span_id: str, name: str, duration_s: float, success: bool):
    from opentelemetry.sdk.trace import ReadableSpan
    from opentelemetry.trace import SpanContext, TraceFlags, SpanKind
    from opentelemetry.sdk.trace import Span as SdkSpan

    class FakeSpan:
        def __init__(self):
            self._trace_id = trace_id
            self._span_id = span_id
            self._name = name
            self._start_time = time.time_ns()
            self._end_time = self._start_time + int(duration_s * 1e9)
            self._kind = SpanKind.INTERNAL
            self._attributes = {"success": success, "duration_ms": duration_s * 1000}
            self._status = None
            self._parent = None
            self._resource = None
            self._instrumentation_scope = None

        def get_span_context(self):
            from opentelemetry.trace import SpanContext, TraceFlags
            return SpanContext(
                trace_id=int(hash(trace_id)) % 2**128,
                span_id=int(hash(span_id)) % 2**64,
                is_remote=False,
                trace_flags=TraceFlags(1),
            )

        @property
        def name(self): return self._name

        @property
        def start_time(self): return self._start_time

        @property
        def end_time(self): return self._end_time

        @property
        def kind(self): return self._kind

        @property
        def attributes(self): return self._attributes

        @property
        def status(self): return self._status

        @property
        def parent(self): return self._parent

        @property
        def resource(self): return self._resource

        @property
        def instrumentation_scope(self): return self._instrumentation_scope

    return FakeSpan()
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
uv run python -m pytest tests/test_trace_store.py -v
```
Expected: ImportError for `src.monitoring.trace_store`

- [ ] **Step 3: Implement TraceStore**

```python
# src/monitoring/trace_store.py
import threading
import time
from collections import defaultdict, deque
from typing import Any

from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SpanExporter

_store: "TraceStore | None" = None


class TraceStore(SpanExporter):
    def __init__(self, maxlen: int = 200):
        self.maxlen = maxlen
        self._traces: dict[str, dict[str, Any]] = {}
        self._order: deque[str] = deque(maxlen=maxlen)

    def export(self, spans, timeout_millis=30000):
        for span in spans:
            ctx = span.get_span_context()
            trace_id = format(ctx.trace_id, "032x")
            span_id = format(ctx.span_id, "016x")
            attrs = dict(span.attributes or {})
            duration_ns = span.end_time - span.start_time
            duration_ms = duration_ns / 1_000_000
            success = attrs.get("success", True)
            error = not success

            if trace_id not in self._traces:
                self._traces[trace_id] = {
                    "trace_id": trace_id,
                    "start_time": span.start_time,
                    "duration_ms": duration_ms,
                    "span_count": 0,
                    "error": error,
                    "spans": [],
                }
                self._order.append(trace_id)
            else:
                existing = self._traces[trace_id]
                existing["start_time"] = min(existing["start_time"], span.start_time)
                existing["duration_ms"] = max(existing["duration_ms"], duration_ms)
                existing["error"] = existing["error"] or error

            self._traces[trace_id]["span_count"] += 1
            self._traces[trace_id]["spans"].append({
                "span_id": span_id,
                "name": span.name,
                "start_time": span.start_time,
                "duration_ms": duration_ms,
                "attributes": attrs,
                "error": error,
            })
        return True

    def shutdown(self):
        pass

    def get_traces(
        self,
        min_duration_ms: float = 0,
        error_only: bool = False,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        result = []
        for tid in reversed(self._order):
            t = self._traces[tid]
            if error_only and not t["error"]:
                continue
            if t["duration_ms"] < min_duration_ms:
                continue
            result.append({
                "trace_id": t["trace_id"],
                "start_time": t["start_time"],
                "duration_ms": round(t["duration_ms"], 2),
                "span_count": t["span_count"],
                "error": t["error"],
            })
            if len(result) >= limit:
                break
        return result

    def get_trace_detail(self, trace_id: str) -> dict[str, Any] | None:
        t = self._traces.get(trace_id)
        if not t:
            return None
        return {
            "trace_id": t["trace_id"],
            "duration_ms": round(t["duration_ms"], 2),
            "span_count": t["span_count"],
            "error": t["error"],
            "spans": sorted(t["spans"], key=lambda s: s["start_time"]),
        }


def init_trace_store(maxlen: int = 200) -> TraceStore:
    global _store
    _store = TraceStore(maxlen=maxlen)
    return _store


def get_traces(min_duration_ms: float = 0, error_only: bool = False, limit: int = 50) -> list[dict]:
    global _store
    if _store is None:
        return []
    return _store.get_traces(min_duration_ms=min_duration_ms, error_only=error_only, limit=limit)


def get_trace_detail(trace_id: str) -> dict | None:
    global _store
    if _store is None:
        return None
    return _store.get_trace_detail(trace_id)
```

- [ ] **Step 4: Run tests**

Run:
```bash
uv run python -m pytest tests/test_trace_store.py -v
```
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add src/monitoring/trace_store.py tests/test_trace_store.py
git commit -m "feat: add TraceStore in-memory span storage"
```

---
### Task 3: Pipeline CRUD backend endpoints

**Files:**
- Create: `src/api/routes/admin/pipelines.py`
- Test: `tests/test_admin_pipelines.py`

**Interfaces:**
- Consumes: `PipelineRegistry` (singleton from `src.pipeline.registry`)
- Produces: FastAPI router at `/api/v1/pipelines` with GET list, GET dag, POST create, PUT update, DELETE

- [ ] **Step 1: Write tests**

```python
# tests/test_admin_pipelines.py
from fastapi.testclient import TestClient
from src.api.app import app

client = TestClient(app)

def _token():
    resp = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"})
    return resp.json()["access_token"]

_headers = {}

def setup_module():
    global _headers
    _headers = {"Authorization": f"Bearer {_token()}"}


def test_list_pipelines():
    resp = client.get("/api/v1/pipelines", headers=_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "pipelines" in data
    assert len(data["pipelines"]) >= 5


def test_get_pipeline_dag():
    resp = client.get("/api/v1/pipelines/object_detection", headers=_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "object_detection"
    assert "nodes" in data
    assert "entry_nodes" in data


def test_get_pipeline_not_found():
    resp = client.get("/api/v1/pipelines/nonexistent", headers=_headers)
    assert resp.status_code == 404


def test_create_pipeline():
    payload = {
        "name": "test_pipeline",
        "nodes": [
            {"node_id": "detect", "node_type": "model_inference", "config": {"model": "object_detection"}, "depends_on": []},
        ],
        "entry_nodes": ["detect"],
        "output_node": "detect",
    }
    resp = client.post("/api/v1/pipelines", json=payload, headers=_headers)
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    # verify it was created
    resp2 = client.get("/api/v1/pipelines/test_pipeline", headers=_headers)
    assert resp2.status_code == 200


def test_create_pipeline_duplicate():
    payload = {
        "name": "test_pipeline",
        "nodes": [
            {"node_id": "detect", "node_type": "model_inference", "config": {"model": "object_detection"}, "depends_on": []},
        ],
        "entry_nodes": ["detect"],
        "output_node": "detect",
    }
    resp = client.post("/api/v1/pipelines", json=payload, headers=_headers)
    assert resp.status_code == 409


def test_create_pipeline_invalid_dag():
    payload = {
        "name": "invalid_dag",
        "nodes": [
            {"node_id": "a", "node_type": "model_inference", "config": {}, "depends_on": ["b"]},
        ],
        "entry_nodes": ["a"],
        "output_node": "a",
    }
    resp = client.post("/api/v1/pipelines", json=payload, headers=_headers)
    assert resp.status_code == 400


def test_update_pipeline():
    payload = {
        "nodes": [
            {"node_id": "detect", "node_type": "model_inference", "config": {"model": "face_recognition"}, "depends_on": []},
        ],
        "entry_nodes": ["detect"],
        "output_node": "detect",
    }
    resp = client.put("/api/v1/pipelines/test_pipeline", json=payload, headers=_headers)
    assert resp.status_code == 200
    resp2 = client.get("/api/v1/pipelines/test_pipeline", headers=_headers)
    nodes = resp2.json()["nodes"]
    assert nodes["detect"]["config"]["model"] == "face_recognition"


def test_delete_pipeline():
    resp = client.delete("/api/v1/pipelines/test_pipeline", headers=_headers)
    assert resp.status_code == 200
    resp2 = client.get("/api/v1/pipelines/test_pipeline", headers=_headers)
    assert resp2.status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
uv run python -m pytest tests/test_admin_pipelines.py -v
```
Expected: ImportError for `src.api.routes.admin.pipelines`

- [ ] **Step 3: Implement pipeline CRUD endpoints**

```python
# src/api/routes/admin/pipelines.py
from fastapi import APIRouter, HTTPException

from src.pipeline.dag import DAGDefinition, DAGNode, NodeType
from src.pipeline.registry import PipelineRegistry

router = APIRouter(prefix="/api/v1/pipelines", tags=["admin-pipelines"])

_registry: PipelineRegistry | None = None


def init_pipeline_registry(registry: PipelineRegistry) -> None:
    global _registry
    _registry = registry


@router.get("")
async def list_pipelines() -> dict:
    if _registry is None:
        return {"pipelines": []}
    names = _registry.list()
    result = []
    for name in names:
        dag = _registry.get(name)
        if dag:
            result.append({
                "name": dag.name,
                "node_count": len(dag.nodes),
                "entry_nodes": dag.entry_nodes,
                "output_node": dag.output_node,
            })
    return {"pipelines": result}


@router.get("/{name}")
async def get_pipeline_dag(name: str) -> dict:
    if _registry is None:
        raise HTTPException(404, "Registry not initialized")
    dag = _registry.get(name)
    if dag is None:
        raise HTTPException(404, f"Pipeline '{name}' not found")
    return {
        "name": dag.name,
        "nodes": {nid: {"node_id": n.node_id, "node_type": n.node_type.value, "config": n.config, "depends_on": n.depends_on} for nid, n in dag.nodes.items()},
        "entry_nodes": dag.entry_nodes,
        "output_node": dag.output_node,
    }


@router.post("")
async def create_pipeline(body: dict) -> dict:
    if _registry is None:
        raise HTTPException(500, "Registry not initialized")
    name = body.get("name", "")
    if _registry.get(name) is not None:
        raise HTTPException(409, f"Pipeline '{name}' already exists")
    dag = _build_dag(body)
    _registry.register(name, dag)
    return {"ok": True}


@router.put("/{name}")
async def update_pipeline(name: str, body: dict) -> dict:
    if _registry is None:
        raise HTTPException(500, "Registry not initialized")
    if _registry.get(name) is None:
        raise HTTPException(404, f"Pipeline '{name}' not found")
    _registry.unregister(name)
    dag = _build_dag({**body, "name": name})
    _registry.register(name, dag)
    return {"ok": True}


@router.delete("/{name}")
async def delete_pipeline(name: str) -> dict:
    if _registry is None:
        raise HTTPException(500, "Registry not initialized")
    if _registry.get(name) is None:
        raise HTTPException(404, f"Pipeline '{name}' not found")
    _registry.unregister(name)
    return {"ok": True}


def _build_dag(body: dict) -> DAGDefinition:
    name = body.get("name", "")
    nodes_data = body.get("nodes", [])
    entry_nodes = body.get("entry_nodes", [])
    output_node = body.get("output_node", "")

    dag = DAGDefinition(name=name, entry_nodes=entry_nodes, output_node=output_node)
    for nd in nodes_data:
        try:
            ntype = NodeType(nd["node_type"])
        except ValueError:
            raise HTTPException(400, f"Invalid node_type: {nd['node_type']}")
        node = DAGNode(
            node_id=nd["node_id"],
            node_type=ntype,
            config=nd.get("config", {}),
            depends_on=nd.get("depends_on", []),
        )
        dag.add_node(node)
    if not dag.validate():
        raise HTTPException(400, "Invalid DAG: dependency references non-existent node")
    return dag
```

- [ ] **Step 4: Run tests**

```bash
uv run python -m pytest tests/test_admin_pipelines.py -v
```
Expected: 8 passed

- [ ] **Step 5: Register in app.py**

Edit `src/api/app.py`:
1. Add import: `from src.api.routes.admin.pipelines import router as admin_pipelines_router, init_pipeline_registry`
2. Add `app.include_router(admin_pipelines_router)` after existing admin routers
3. In `_init_components`, after `pipeline_registry` is created, add `init_pipeline_registry(pipeline_registry)`

- [ ] **Step 6: Commit**

```bash
git add src/api/routes/admin/pipelines.py tests/test_admin_pipelines.py src/api/app.py
git commit -m "feat: add pipeline CRUD backend endpoints"
```

---
### Task 4: Log query API endpoint + Wire LogBuffer into lifespan

**Files:**
- Create: `src/api/routes/admin/logs.py`
- Modify: `src/api/app.py`

**Interfaces:**
- Consumes: `get_logs`, `clear_logs` from `src.monitoring.log_buffer`
- Produces: `GET /api/v1/logs`, `DELETE /api/v1/logs`

- [ ] **Step 1: Write tests**

```python
# tests/test_admin_logs.py
import logging
from fastapi.testclient import TestClient
from src.api.app import app
from src.monitoring.log_buffer import clear_logs, init_log_buffer

client = TestClient(app)

def _token():
    resp = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"})
    return resp.json()["access_token"]

_headers = {}

def setup_module():
    global _headers
    _headers = {"Authorization": f"Bearer {_token()}"}
    clear_logs()
    init_log_buffer(maxlen=200)


def test_get_logs_empty():
    resp = client.get("/api/v1/logs", headers=_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "logs" in data
    assert "total" in data


def test_get_logs_with_entries():
    logging.getLogger("test_logs_api").warning("test warning message")
    logging.getLogger("test_logs_api").info("test info message")
    resp = client.get("/api/v1/logs", headers=_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 2


def test_get_logs_filter_level():
    resp = client.get("/api/v1/logs?level=WARNING", headers=_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert all(e["level"] == "WARNING" for e in data["logs"])


def test_get_logs_search():
    resp = client.get("/api/v1/logs?q=warning", headers=_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["logs"]) >= 1
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
uv run python -m pytest tests/test_admin_logs.py -v
```
Expected: ImportError for `src.api.routes.admin.logs`

- [ ] **Step 3: Implement log query endpoint**

```python
# src/api/routes/admin/logs.py
from fastapi import APIRouter, Query

from src.monitoring.log_buffer import get_logs, clear_logs

router = APIRouter(prefix="/api/v1/logs", tags=["admin-logs"])


@router.get("")
async def query_logs(
    level: str | None = Query(None, description="Filter by level: DEBUG, INFO, WARNING, ERROR"),
    module: str | None = Query(None, description="Filter by module name (substring match)"),
    q: str | None = Query(None, description="Search in message text"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> dict:
    return get_logs(level=level, module=module, q=q, limit=limit, offset=offset)


@router.delete("")
async def delete_logs() -> dict:
    clear_logs()
    return {"ok": True}
```

- [ ] **Step 4: Register in app.py**

1. Add import: `from src.api.routes.admin.logs import router as admin_logs_router`
2. Add `app.include_router(admin_logs_router)` after existing admin routers
3. In `lifespan`, after component init, call `init_log_buffer(maxlen=2000)` (import from `src.monitoring.log_buffer`)

- [ ] **Step 5: Run tests**

```bash
uv run python -m pytest tests/test_admin_logs.py -v
```
Expected: 4 passed

- [ ] **Step 6: Commit**

```bash
git add src/api/routes/admin/logs.py tests/test_admin_logs.py src/api/app.py
git commit -m "feat: add log query API endpoint"
```

---
### Task 5: Trace query API endpoint + Wire TraceStore into lifespan

**Files:**
- Create: `src/api/routes/admin/traces.py`
- Modify: `src/api/app.py`, `src/monitoring/tracing.py`

**Interfaces:**
- Consumes: `get_traces`, `get_trace_detail` from `src.monitoring.trace_store`
- Produces: `GET /api/v1/traces`, `GET /api/v1/traces/{trace_id}`

- [ ] **Step 1: Wire TraceStore into OpenTelemetry tracing**

In `src/monitoring/tracing.py`, add a new function `add_trace_store_exporter(store)` that adds the TraceStore as another SpanProcessor, and export `init_trace_store_in_otel`.

- [ ] **Step 2: Write tests**

```python
# tests/test_admin_traces.py
from fastapi.testclient import TestClient
from src.api.app import app

client = TestClient(app)

def _token():
    resp = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"})
    return resp.json()["access_token"]

_headers = {}

def setup_module():
    global _headers
    _headers = {"Authorization": f"Bearer {_token()}"}


def test_get_traces():
    resp = client.get("/api/v1/traces", headers=_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "traces" in data


def test_get_trace_detail_not_found():
    resp = client.get("/api/v1/traces/nonexistent_trace_id", headers=_headers)
    assert resp.status_code == 404
```

- [ ] **Step 3: Implement trace query endpoint**

```python
# src/api/routes/admin/traces.py
from fastapi import APIRouter, HTTPException, Query

from src.monitoring.trace_store import get_traces, get_trace_detail

router = APIRouter(prefix="/api/v1/traces", tags=["admin-traces"])


@router.get("")
async def list_traces(
    min_duration_ms: float = Query(0, ge=0),
    error_only: bool = Query(False),
    limit: int = Query(50, ge=1, le=500),
) -> dict:
    traces = get_traces(min_duration_ms=min_duration_ms, error_only=error_only, limit=limit)
    return {"traces": traces}


@router.get("/{trace_id}")
async def trace_detail(trace_id: str) -> dict:
    detail = get_trace_detail(trace_id)
    if detail is None:
        raise HTTPException(404, f"Trace '{trace_id}' not found")
    return detail
```

- [ ] **Step 4: Register in app.py**

1. Add import: `from src.api.routes.admin.traces import router as admin_traces_router`
2. Add `app.include_router(admin_traces_router)`
3. Add import: `from src.monitoring.trace_store import init_trace_store`
4. In `_init_components` or `lifespan`, add: `store = init_trace_store(maxlen=500)` then wire it into tracing

- [ ] **Step 5: Run tests**

```bash
uv run python -m pytest tests/test_admin_traces.py -v
```
Expected: 2 passed

- [ ] **Step 6: Full backend test suite**

```bash
uv run python -m pytest tests/ -v --tb=short
```
Expected: all pass (existing 102 + 20 new = ~122)

- [ ] **Step 7: Commit**

```bash
git add src/api/routes/admin/traces.py tests/test_admin_traces.py src/api/app.py src/monitoring/tracing.py
git commit -m "feat: add trace query API endpoints"
```

---
### Task 6: Frontend Pipelines page with DAG editor

**Files:**
- Create: `frontend/src/api/pipelines.ts`, `frontend/src/stores/pipelines.ts`, `frontend/src/views/Pipelines/Index.vue`
- Modify: `frontend/src/router/index.ts`, `frontend/src/components/Sidebar.vue`

- [ ] **Step 1: Create API client**

```typescript
// frontend/src/api/pipelines.ts
import client from './client'

export interface PipelineNode {
  node_id: string
  node_type: string
  config: Record<string, any>
  depends_on: string[]
}

export interface PipelineDAG {
  name: string
  nodes: Record<string, PipelineNode>
  entry_nodes: string[]
  output_node: string
}

export interface PipelineSummary {
  name: string
  node_count: number
  entry_nodes: string[]
  output_node: string
}

export async function fetchPipelines() {
  const res = await client.get<{ pipelines: PipelineSummary[] }>('/api/v1/pipelines')
  return res.data.pipelines
}

export async function fetchPipelineDAG(name: string) {
  const res = await client.get<PipelineDAG>(`/api/v1/pipelines/${name}`)
  return res.data
}

export async function createPipeline(name: string, dag: Partial<PipelineDAG>) {
  const res = await client.post('/api/v1/pipelines', { name, ...dag })
  return res.data
}

export async function updatePipeline(name: string, dag: Partial<PipelineDAG>) {
  const res = await client.put(`/api/v1/pipelines/${name}`, dag)
  return res.data
}

export async function deletePipeline(name: string) {
  const res = await client.delete(`/api/v1/pipelines/${name}`)
  return res.data
}
```

- [ ] **Step 2: Create store**

```typescript
// frontend/src/stores/pipelines.ts
import { defineStore } from 'pinia'
import { ref } from 'vue'
import {
  fetchPipelines,
  fetchPipelineDAG,
  createPipeline,
  updatePipeline,
  deletePipeline,
  type PipelineSummary,
  type PipelineDAG,
} from '@/api/pipelines'

export const usePipelineStore = defineStore('pipelines', () => {
  const pipelines = ref<PipelineSummary[]>([])
  const currentDAG = ref<PipelineDAG | null>(null)
  const loading = ref(false)
  const saving = ref(false)

  async function load() {
    loading.value = true
    try {
      pipelines.value = await fetchPipelines()
    } finally {
      loading.value = false
    }
  }

  async function loadDAG(name: string) {
    loading.value = true
    try {
      currentDAG.value = await fetchPipelineDAG(name)
    } finally {
      loading.value = false
    }
  }

  async function create(name: string, dag: Partial<PipelineDAG>) {
    saving.value = true
    try {
      await createPipeline(name, dag)
      await load()
    } finally {
      saving.value = false
    }
  }

  async function update(name: string, dag: Partial<PipelineDAG>) {
    saving.value = true
    try {
      await updatePipeline(name, dag)
      await loadDAG(name)
    } finally {
      saving.value = false
    }
  }

  async function remove(name: string) {
    saving.value = true
    try {
      await deletePipeline(name)
      if (currentDAG.value?.name === name) currentDAG.value = null
      await load()
    } finally {
      saving.value = false
    }
  }

  return { pipelines, currentDAG, loading, saving, load, loadDAG, create, update, remove }
})
```

- [ ] **Step 3: Create Pipelines page**

```vue
<!-- frontend/src/views/Pipelines/Index.vue -->
<template>
  <div>
    <h2 style="margin-bottom:16px">流水线管理</h2>
    <el-button type="primary" style="margin-bottom:12px" @click="showCreate = true">新建流水线</el-button>

    <el-dialog v-model="showCreate" title="新建流水线" width="500px">
      <el-form>
        <el-form-item label="名称">
          <el-input v-model="newName" placeholder="pipeline_name" />
        </el-form-item>
        <el-form-item label="入口节点">
          <el-input v-model="newEntry" placeholder="entry_node_id" />
        </el-form-item>
        <el-form-item label="输出节点">
          <el-input v-model="newOutput" placeholder="output_node_id" />
        </el-form-item>
        <el-form-item label="节点列表 (JSON)">
          <el-input v-model="newNodesJson" type="textarea" :rows="6" placeholder='[{"node_id":"detect","node_type":"model_inference","config":{"model":"object_detection"},"depends_on":[]}]' />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreate = false">取消</el-button>
        <el-button type="primary" :loading="store.saving" @click="handleCreate">创建</el-button>
      </template>
    </el-dialog>

    <el-table :data="store.pipelines" v-loading="store.loading" stripe style="width:100%">
      <el-table-column prop="name" label="名称" />
      <el-table-column prop="node_count" label="节点数" width="100" />
      <el-table-column label="入口节点" width="200">
        <template #default="{ row }">{{ row.entry_nodes?.join(', ') }}</template>
      </el-table-column>
      <el-table-column label="操作" width="280">
        <template #default="{ row }">
          <el-button size="small" @click="viewDAG(row.name)">查看 DAG</el-button>
          <el-button size="small" @click="handleEdit(row.name)">编辑</el-button>
          <el-popconfirm title="确定删除？" @confirm="store.remove(row.name)">
            <template #reference>
              <el-button size="small" type="danger">删除</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="showDAG" title="DAG 编辑器" width="800px" top="5vh">
      <div v-if="store.currentDAG">
        <el-tag style="margin-bottom:12px">{{ store.currentDAG.name }}</el-tag>
        <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px">
          <div v-for="(node, nid) in store.currentDAG.nodes" :key="nid" class="dag-node">
            <strong>{{ node.node_id }}</strong>
            <el-tag size="small" type="info" style="margin-left:6px">{{ node.node_type }}</el-tag>
            <div v-if="node.depends_on.length" style="font-size:12px;color:#909399;margin-top:4px">
              依赖: {{ node.depends_on.join(', ') }}
            </div>
          </div>
        </div>
        <!-- Canvas-based DAG visualization -->
        <canvas ref="dagCanvas" width="740" height="400" style="border:1px solid #dcdfe6;border-radius:4px;width:100%"></canvas>
      </div>
      <template #footer>
        <el-button @click="showDAG = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import { usePipelineStore } from '@/stores/pipelines'

const store = usePipelineStore()
const showCreate = ref(false)
const showDAG = ref(false)
const newName = ref('')
const newEntry = ref('')
const newOutput = ref('')
const newNodesJson = ref('')
const dagCanvas = ref<HTMLCanvasElement | null>(null)

onMounted(() => store.load())

async function viewDAG(name: string) {
  await store.loadDAG(name)
  showDAG.value = true
  await nextTick()
  drawDAG()
}

async function handleEdit(name: string) {
  newName.value = name
  await store.loadDAG(name)
  if (store.currentDAG) {
    newEntry.value = store.currentDAG.entry_nodes.join(', ')
    newOutput.value = store.currentDAG.output_node
    newNodesJson.value = JSON.stringify(Object.values(store.currentDAG.nodes), null, 2)
  }
  showCreate.value = true
}

async function handleCreate() {
  let nodes: any[]
  try {
    nodes = JSON.parse(newNodesJson.value || '[]')
  } catch {
    ElMessage.error('节点 JSON 格式错误')
    return
  }
  const dag = {
    nodes,
    entry_nodes: newEntry.value ? newEntry.value.split(',').map(s => s.trim()).filter(Boolean) : [],
    output_node: newOutput.value,
  }
  const existing = store.pipelines.find(p => p.name === newName.value)
  if (existing) {
    await store.update(newName.value, dag)
    ElMessage.success('流水线已更新')
  } else {
    await store.create(newName.value, dag)
    ElMessage.success('流水线已创建')
  }
  showCreate.value = false
}

function drawDAG() {
  const canvas = dagCanvas.value
  if (!canvas || !store.currentDAG) return
  const ctx = canvas.getContext('2d')
  if (!ctx) return
  ctx.clearRect(0, 0, canvas.width, canvas.height)
  const nodes = Object.values(store.currentDAG.nodes)
  if (!nodes.length) return
  const cols = Math.ceil(Math.sqrt(nodes.length))
  const boxW = 140
  const boxH = 50
  const gapX = 40
  const gapY = 60
  const startX = 30
  const startY = 30
  const positions: Record<string, { x: number; y: number }> = {}

  nodes.forEach((node, i) => {
    const col = i % cols
    const row = Math.floor(i / cols)
    const x = startX + col * (boxW + gapX)
    const y = startY + row * (boxH + gapY)
    positions[node.node_id] = { x, y }

    // draw box
    ctx.fillStyle = '#ecf5ff'
    ctx.strokeStyle = '#409eff'
    ctx.lineWidth = 1.5
    ctx.beginPath()
    ctx.roundRect(x, y, boxW, boxH, 6)
    ctx.fill()
    ctx.stroke()

    // label
    ctx.fillStyle = '#303133'
    ctx.font = '12px sans-serif'
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    ctx.fillText(node.node_id, x + boxW / 2, y + boxH / 2)

    // draw dependency arrows
    node.depends_on.forEach((depId) => {
      const from = positions[depId]
      if (!from) return
      const sx = from.x + boxW / 2
      const sy = from.y + boxH
      const ex = x + boxW / 2
      const ey = y
      ctx.strokeStyle = '#c0c4cc'
      ctx.lineWidth = 1
      ctx.beginPath()
      ctx.moveTo(sx, sy)
      ctx.lineTo(ex, ey)
      ctx.stroke()
      // arrowhead
      const angle = Math.atan2(ey - sy, ex - sx)
      ctx.fillStyle = '#c0c4cc'
      ctx.beginPath()
      ctx.moveTo(ex, ey)
      ctx.lineTo(ex - 8 * Math.cos(angle - 0.4), ey - 8 * Math.sin(angle - 0.4))
      ctx.lineTo(ex - 8 * Math.cos(angle + 0.4), ey - 8 * Math.sin(angle + 0.4))
      ctx.closePath()
      ctx.fill()
    })
  })
}
</script>

<style scoped>
.dag-node {
  border: 1px solid #dcdfe6;
  border-radius: 6px;
  padding: 8px 12px;
  background: #fafafa;
}
</style>
```

- [ ] **Step 4: Register route + sidebar**

In `frontend/src/router/index.ts`, add to children:
```typescript
{ path: 'pipelines', name: 'Pipelines', component: () => import('@/views/Pipelines/Index.vue') },
```

In `frontend/src/components/Sidebar.vue`, add after Agent:
```html
<el-menu-item index="/pipelines">
  <el-icon><Connection /></el-icon><span>流水线管理</span>
</el-menu-item>
```
And import `Connection` from `@element-plus/icons-vue`.

- [ ] **Step 5: Verify frontend build**

```bash
cd frontend && npm run build
```
Expected: Build succeeds with no errors

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api/pipelines.ts frontend/src/stores/pipelines.ts frontend/src/views/Pipelines/Index.vue frontend/src/router/index.ts frontend/src/components/Sidebar.vue
git commit -m "feat: add Pipeline Management page with DAG editor"
```

---
### Task 7: Frontend Logs page

**Files:**
- Create: `frontend/src/api/logs.ts`, `frontend/src/stores/logs.ts`, `frontend/src/views/Logs/Index.vue`
- Modify: `frontend/src/router/index.ts`, `frontend/src/components/Sidebar.vue`

- [ ] **Step 1: Create API client**

```typescript
// frontend/src/api/logs.ts
import client from './client'

export interface LogEntry {
  timestamp: string
  level: string
  logger: string
  message: string
  module: string
  func: string
  line: number
}

export interface LogQueryResult {
  logs: LogEntry[]
  total: number
}

export async function queryLogs(params: {
  level?: string
  module?: string
  q?: string
  limit?: number
  offset?: number
}) {
  const res = await client.get<LogQueryResult>('/api/v1/logs', { params })
  return res.data
}

export async function clearLogs() {
  await client.delete('/api/v1/logs')
}
```

- [ ] **Step 2: Create store**

```typescript
// frontend/src/stores/logs.ts
import { defineStore } from 'pinia'
import { ref } from 'vue'
import { queryLogs, clearLogs, type LogEntry } from '@/api/logs'

export const useLogStore = defineStore('logs', () => {
  const logs = ref<LogEntry[]>([])
  const total = ref(0)
  const loading = ref(false)
  const level = ref('')
  const module = ref('')
  const search = ref('')

  async function load() {
    loading.value = true
    try {
      const result = await queryLogs({
        level: level.value || undefined,
        module: module.value || undefined,
        q: search.value || undefined,
        limit: 200,
      })
      logs.value = result.logs
      total.value = result.total
    } finally {
      loading.value = false
    }
  }

  async function clear() {
    await clearLogs()
    await load()
  }

  return { logs, total, loading, level, module, search, load, clear }
})
```

- [ ] **Step 3: Create Logs page**

```vue
<!-- frontend/src/views/Logs/Index.vue -->
<template>
  <div>
    <h2 style="margin-bottom:16px">日志查询</h2>
    <div style="display:flex;gap:12px;margin-bottom:12px;flex-wrap:wrap">
      <el-select v-model="store.level" clearable placeholder="日志级别" style="width:140px" @change="store.load()">
        <el-option label="DEBUG" value="DEBUG" />
        <el-option label="INFO" value="INFO" />
        <el-option label="WARNING" value="WARNING" />
        <el-option label="ERROR" value="ERROR" />
      </el-select>
      <el-input v-model="store.module" placeholder="模块名" style="width:200px" clearable @change="store.load()" />
      <el-input v-model="store.search" placeholder="搜索关键词" style="width:240px" clearable @change="store.load()" />
      <el-button @click="store.load()" :loading="store.loading">查询</el-button>
      <el-button @click="store.clear()">清空日志</el-button>
    </div>
    <el-table :data="store.logs" v-loading="store.loading" stripe style="width:100%" max-height="700px" size="small">
      <el-table-column prop="timestamp" label="时间" width="180" />
      <el-table-column prop="level" label="级别" width="90">
        <template #default="{ row }">
          <el-tag :type="levelType(row.level)" size="small">{{ row.level }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="logger" label="Logger" width="200" />
      <el-table-column prop="message" label="消息" min-width="300" show-overflow-tooltip />
    </el-table>
    <div style="margin-top:8px;color:#909399;font-size:13px">共 {{ store.total }} 条日志</div>
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { useLogStore } from '@/stores/logs'

const store = useLogStore()
onMounted(() => store.load())

function levelType(level: string) {
  if (level === 'ERROR') return 'danger'
  if (level === 'WARNING') return 'warning'
  if (level === 'DEBUG') return 'info'
  return ''
}
</script>
```

- [ ] **Step 4: Register route + sidebar**

In router, add: `{ path: 'logs', name: 'Logs', component: () => import('@/views/Logs/Index.vue') }`

In Sidebar, add:
```html
<el-menu-item index="/logs">
  <el-icon><Document /></el-icon><span>日志查询</span>
</el-menu-item>
```
Import `Document` from icons.

- [ ] **Step 5: Verify frontend build**

```bash
cd frontend && npm run build
```
Expected: Build succeeds

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api/logs.ts frontend/src/stores/logs.ts frontend/src/views/Logs/Index.vue frontend/src/router/index.ts frontend/src/components/Sidebar.vue
git commit -m "feat: add Logs page with filtering"
```

---
### Task 8: Frontend Traces page with detail drill-down

**Files:**
- Create: `frontend/src/api/traces.ts`, `frontend/src/stores/traces.ts`, `frontend/src/views/Traces/Index.vue`, `frontend/src/views/Traces/Detail.vue`
- Modify: `frontend/src/router/index.ts`, `frontend/src/components/Sidebar.vue`

- [ ] **Step 1: Create API client**

```typescript
// frontend/src/api/traces.ts
import client from './client'

export interface TraceSummary {
  trace_id: string
  start_time: number
  duration_ms: number
  span_count: number
  error: boolean
}

export interface SpanData {
  span_id: string
  name: string
  start_time: number
  duration_ms: number
  attributes: Record<string, any>
  error: boolean
}

export interface TraceDetail {
  trace_id: string
  duration_ms: number
  span_count: number
  error: boolean
  spans: SpanData[]
}

export async function fetchTraces(params: {
  min_duration_ms?: number
  error_only?: boolean
  limit?: number
}) {
  const res = await client.get<{ traces: TraceSummary[] }>('/api/v1/traces', { params })
  return res.data.traces
}

export async function fetchTraceDetail(traceId: string) {
  const res = await client.get<TraceDetail>(`/api/v1/traces/${traceId}`)
  return res.data
}
```

- [ ] **Step 2: Create store**

```typescript
// frontend/src/stores/traces.ts
import { defineStore } from 'pinia'
import { ref } from 'vue'
import { fetchTraces, fetchTraceDetail, type TraceSummary, type TraceDetail } from '@/api/traces'

export const useTraceStore = defineStore('traces', () => {
  const traces = ref<TraceSummary[]>([])
  const detail = ref<TraceDetail | null>(null)
  const loading = ref(false)
  const errorOnly = ref(false)
  const minDuration = ref(0)

  async function load() {
    loading.value = true
    try {
      traces.value = await fetchTraces({
        error_only: errorOnly.value,
        min_duration_ms: minDuration.value || undefined,
        limit: 50,
      })
    } finally {
      loading.value = false
    }
  }

  async function loadDetail(traceId: string) {
    loading.value = true
    try {
      detail.value = await fetchTraceDetail(traceId)
    } finally {
      loading.value = false
    }
  }

  return { traces, detail, loading, errorOnly, minDuration, load, loadDetail }
})
```

- [ ] **Step 3: Create Traces list page**

```vue
<!-- frontend/src/views/Traces/Index.vue -->
<template>
  <div>
    <h2 style="margin-bottom:16px">链路追踪</h2>
    <div style="display:flex;gap:12px;margin-bottom:12px">
      <el-checkbox v-model="store.errorOnly" label="仅显示错误" @change="store.load()" />
      <el-input v-model.number="store.minDuration" placeholder="最小耗时 (ms)" style="width:160px" clearable @change="store.load()" />
      <el-button @click="store.load()" :loading="store.loading">刷新</el-button>
    </div>
    <el-table :data="store.traces" v-loading="store.loading" stripe style="width:100%">
      <el-table-column prop="trace_id" label="Trace ID" width="280">
        <template #default="{ row }">
          <router-link :to="`/traces/${row.trace_id}`" style="font-family:monospace;font-size:13px">{{ row.trace_id.substring(0, 16) }}...</router-link>
        </template>
      </el-table-column>
      <el-table-column prop="duration_ms" label="耗时 (ms)" width="120">
        <template #default="{ row }">{{ row.duration_ms.toFixed(2) }}</template>
      </el-table-column>
      <el-table-column prop="span_count" label="Span 数" width="100" />
      <el-table-column label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="row.error ? 'danger' : 'success'" size="small">{{ row.error ? '异常' : '正常' }}</el-tag>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { useTraceStore } from '@/stores/traces'

const store = useTraceStore()
onMounted(() => store.load())
</script>
```

- [ ] **Step 4: Create Trace detail page**

```vue
<!-- frontend/src/views/Traces/Detail.vue -->
<template>
  <div>
    <el-button text @click="$router.push('/traces')">&lt; 返回列表</el-button>
    <div v-if="store.detail" v-loading="store.loading" style="margin-top:12px">
      <el-card>
        <template #header>
          <span>Trace: <code style="font-size:13px">{{ store.detail.trace_id }}</code></span>
          <el-tag :type="store.detail.error ? 'danger' : 'success'" size="small" style="margin-left:12px">
            {{ store.detail.error ? '异常' : '正常' }}
          </el-tag>
        </template>
        <div>总耗时: <strong>{{ store.detail.duration_ms.toFixed(2) }} ms</strong></div>
        <div>Span 数量: <strong>{{ store.detail.span_count }}</strong></div>
      </el-card>

      <h3 style="margin:16px 0 8px">Span 详情</h3>
      <el-table :data="store.detail.spans" stripe style="width:100%">
        <el-table-column prop="span_id" label="Span ID" width="200">
          <template #default="{ row }"><code>{{ row.span_id.substring(0, 12) }}...</code></template>
        </el-table-column>
        <el-table-column prop="name" label="操作" width="200" />
        <el-table-column label="耗时" width="200">
          <template #default="{ row }">
            <div style="display:flex;align-items:center;gap:8px">
              <div :style="{ width: (row.duration_ms / store.detail!.duration_ms * 200) + 'px', height:'16px', background: row.error ? '#f56c6c' : '#409eff', borderRadius:'3px', minWidth:'4px' }"></div>
              <span>{{ row.duration_ms.toFixed(2) }}ms</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="80">
          <template #default="{ row }">
            <el-tag :type="row.error ? 'danger' : 'success'" size="small">{{ row.error ? 'ERR' : 'OK' }}</el-tag>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useTraceStore } from '@/stores/traces'

const route = useRoute()
const store = useTraceStore()

onMounted(async () => {
  await store.loadDetail(route.params.traceId as string)
})
</script>
```

- [ ] **Step 5: Register routes + sidebar**

In router, add to children:
```typescript
{ path: 'logs', name: 'Logs', component: () => import('@/views/Logs/Index.vue') },
{ path: 'traces', name: 'Traces', component: () => import('@/views/Traces/Index.vue') },
{ path: 'traces/:traceId', name: 'TraceDetail', component: () => import('@/views/Traces/Detail.vue') },
```

In Sidebar, add after 流水线管理:
```html
<el-menu-item index="/logs">
  <el-icon><Document /></el-icon><span>日志查询</span>
</el-menu-item>
<el-menu-item index="/traces">
  <el-icon><Link /></el-icon><span>链路追踪</span>
</el-menu-item>
```
Import `Document`, `Link` from icons.

- [ ] **Step 6: Verify frontend build**

```bash
cd frontend && npm run build
```
Expected: Build succeeds

- [ ] **Step 7: Run full test suite**

```bash
uv run python -m pytest tests/ -v --tb=short
```
Expected: All tests pass

- [ ] **Step 8: Commit**

```bash
git add frontend/src/api/traces.ts frontend/src/stores/traces.ts frontend/src/views/Traces/Index.vue frontend/src/views/Traces/Detail.vue frontend/src/router/index.ts frontend/src/components/Sidebar.vue
git commit -m "feat: add Traces page with detail drill-down"
```

---
## Full Verification

```bash
# Backend tests
uv run python -m pytest tests/ -v --tb=short

# Frontend build
cd frontend && npm run build
```

Expected: All backend tests pass, frontend build succeeds.

## Commit ordering

1. `feat: add LogBuffer in-memory ring buffer for structured logs`
2. `feat: add TraceStore in-memory span storage`
3. `feat: add pipeline CRUD backend endpoints`
4. `feat: add log query API endpoint`
5. `feat: add trace query API endpoints`
6. `feat: add Pipeline Management page with DAG editor`
7. `feat: add Logs page with filtering`
8. `feat: add Traces page with detail drill-down`
