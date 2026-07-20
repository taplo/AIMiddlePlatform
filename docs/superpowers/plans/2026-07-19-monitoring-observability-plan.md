# Monitoring & Observability Enhancement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix 4 existing monitoring issues and add 6 enhancements to the monitoring & observability infrastructure.

**Architecture:** Incremental fixes to existing `src/monitoring/` package. Register `metrics_middleware` and `setup_json_logging()` in app.py lifespan. Add request logging middleware. Enhance health check endpoint. Add Worker monitoring (JSON logging + Prometheus metrics endpoint). Fix Helm chart paths. Generate Grafana dashboard JSON and PrometheusRule CRD. Apply `trace_async` to 3 key async functions.

**Tech Stack:** FastAPI, prometheus-client, OpenTelemetry, Helm, Grafana

---

## Task 1: Register metrics_middleware in app.py

**Files:**
- Modify: `src/api/app.py`
- Test: `tests/test_monitoring.py` (check existing tests)

The `metrics_middleware` function in `src/monitoring/metrics.py:66` is defined but never registered on the FastAPI app. It uses the low-level ASGI scope interface, so it needs to be registered as `@app.middleware("http")` rather than via `app.add_middleware()` (which expects a class-based middleware).

- [ ] **Step 1: Read existing monitoring tests**

Run:
```bash
cd D:\projects\AIMiddlePlatform
Get-Content tests/test_monitoring.py -Raw
```
Expected: Understand existing test patterns.

- [ ] **Step 2: Register metrics_middleware in app.py**

Edit `src/api/app.py`:
- After line 250 (after `app = FastAPI(...)`), before `CORS middleware`, add raw ASGI middleware registration for metrics

The metrics_middleware function is an ASGI3-style middleware (accepts scope, receive, send). We need to wrap it for FastAPI's `@app.middleware("http")` interface which expects `(request, call_next)`. Since the existing middleware uses the low-level ASGI protocol, the simplest approach is to register it as a raw ASGI middleware using `app.add_middleware()` with a proper ASGI middleware class wrapper, OR convert the approach.

Looking at the code more carefully: the `metrics_middleware` in metrics.py takes `(scope, receive, send)` which is ASGI3 format. FastAPI's `@app.middleware("http")` uses `(request, call_next)` format. The cleanest approach is to add a new `@app.middleware("http")` that wraps the existing metric tracking logic.

Replace the end of `src/api/app.py` (after `app.add_middleware(CORSMiddleware...)` block around line 263):

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Metrics middleware: track request count and latency per (method, path, status)
from src.monitoring.metrics import request_latency, request_total


@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    import time
    start = time.monotonic()
    response = await call_next(request)
    elapsed = time.monotonic() - start
    request_total.labels(method=request.method, path=request.url.path, status=response.status_code).inc()
    request_latency.labels(method=request.method, path=request.url.path).observe(elapsed)
    return response
```

- [ ] **Step 3: Remove the unused raw ASGI `metrics_middleware` function from metrics.py**

Edit `src/monitoring/metrics.py`: Remove lines 66-84 (the raw ASGI `metrics_middleware` function definition), since we now implement it as a FastAPI middleware in app.py.

- [ ] **Step 4: Run tests to verify**

```bash
cd D:\projects\AIMiddlePlatform
uv run pytest tests/ -v --tb=short 2>&1
```
Expected: All tests pass (may have some pre-existing failures unrelated to this change).

- [ ] **Step 5: Commit**

```bash
cd D:\projects\AIMiddlePlatform
git add src/api/app.py src/monitoring/metrics.py
git commit -m "fix: register metrics_middleware on FastAPI app

Previously the metrics middleware was defined as a raw ASGI function
in metrics.py but never registered. Now it's a FastAPI @app.middleware
that tracks app_requests_total and app_request_latency_seconds.
"
```

---

## Task 2: Activate JSON Structured Logging in app.py

**Files:**
- Modify: `src/api/app.py`
- Modify: `src/monitoring/structured_log.py`

- [ ] **Step 1: Make `setup_json_logging()` idempotent**

Edit `src/monitoring/structured_log.py:22-28`: Change to preserve existing handlers if already configured:

```python
def setup_json_logging(level: int = logging.INFO) -> None:
    root = logging.getLogger()
    # Check if already configured with JSON formatter
    for handler in root.handlers:
        if isinstance(handler, logging.StreamHandler) and isinstance(handler.formatter, JSONFormatter):
            return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)
```

- [ ] **Step 2: Call `setup_json_logging()` in app.py lifespan**

Edit `src/api/app.py`:

Add import at line 62 (with existing monitoring imports):
```python
from src.monitoring.structured_log import setup_json_logging
```

Add call in `lifespan()` function at line 89 (before `_init_components()`):
```python
    setup_json_logging()
    _init_components()
    init_log_buffer(maxlen=2000)
```

- [ ] **Step 3: Run tests to verify**

```bash
cd D:\projects\AIMiddlePlatform
uv run pytest tests/ -v --tb=short 2>&1
```
Expected: All tests pass.

- [ ] **Step 4: Commit**

```bash
cd D:\projects\AIMiddlePlatform
git add src/api/app.py src/monitoring/structured_log.py
git commit -m "fix: activate JSON structured logging in app startup

setup_json_logging() was defined but never called in the app lifespan.
Now it's called during startup, and the function is made idempotent
to prevent duplicate handler registration.
"
```

---

## Task 3: Enhanced Health Check Endpoint

**Files:**
- Modify: `src/api/routes/health.py`
- Modify: `src/api/app.py` (to skip auth for health, may already be exempt)

- [ ] **Step 1: Check if `/api/v1/health` is exempt from auth**

Search for `is_exempt_path` usage in app.py to confirm:
```bash
cd D:\projects\AIMiddlePlatform
Select-String "exempt" src/api/app.py src/core/security.py
```
Expected: If already exempt, no auth changes needed.

- [ ] **Step 2: Update health check endpoint**

Edit `src/api/routes/health.py`:
```python
import time
import logging

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_session
from src.core.redis_client import get_redis

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/health", tags=["health"])

_start_time = time.time()


def _uptime() -> float:
    return time.time() - _start_time


@router.get("")
async def health(db: AsyncSession = Depends(get_session)) -> dict:
    checks = {}
    overall = "ok"

    # Database check
    try:
        before = time.monotonic()
        await db.execute(text("SELECT 1"))
        db_latency = (time.monotonic() - before) * 1000
        checks["database"] = {"status": "ok", "latency_ms": round(db_latency, 1)}
    except Exception as e:
        checks["database"] = {"status": "error", "message": str(e)}
        overall = "error"

    # Redis check
    try:
        before = time.monotonic()
        redis = await get_redis()
        await redis.ping()
        redis_latency = (time.monotonic() - before) * 1000
        checks["redis"] = {"status": "ok", "latency_ms": round(redis_latency, 1)}
    except Exception as e:
        checks["redis"] = {"status": "degraded" if overall != "error" else "error", "message": str(e)}
        if overall == "ok":
            overall = "degraded"

    # LLM health check
    try:
        from src.agent.health import get_health_checker
        checker = get_health_checker()
        checks["llm"] = {"status": "ok", "available": checker.available}
    except Exception:
        checks["llm"] = {"status": "degraded", "available": False}
        if overall == "ok":
            overall = "degraded"

    # Model registry check
    try:
        from src.models.registry import ModelRegistry
        registry = ModelRegistry()
        models = registry.list_models()
        checks["model_registry"] = {"status": "ok", "models_count": len(models)}
    except Exception:
        checks["model_registry"] = {"status": "degraded"}
        if overall == "ok":
            overall = "degraded"

    return {
        "status": overall,
        "service": "aimiddleplatform",
        "version": "0.1.0",
        "uptime_seconds": int(_uptime()),
        "checks": checks,
    }
```

- [ ] **Step 3: Verify health endpoint is exempt from auth**

Check `src/api/app.py` line 293:
```python
if is_exempt_path(path) or not (is_admin_path(path) or is_business_path(path)):
    return await call_next(request)
```

The `health` route is at `/api/v1/health` and is mounted as a router with prefix, so it's not under `/admin` or `/business`, meaning it already passes through without auth. No change needed.

- [ ] **Step 4: Run tests to verify**

```bash
cd D:\projects\AIMiddlePlatform
uv run pytest tests/ -v --tb=short 2>&1
```
Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
cd D:\projects\AIMiddlePlatform
git add src/api/routes/health.py
git commit -m "feat: enhanced health check with dependency probes

Health endpoint now checks database (SELECT 1), Redis (PING),
LLM agent availability, and model registry status. Returns
overall status as ok / degraded / error with per-check details.
"
```

---

## Task 4: Request Logging Middleware

**Files:**
- Create: `src/monitoring/request_logger.py`
- Modify: `src/api/app.py`

- [ ] **Step 1: Create request logger middleware**

Create `src/monitoring/request_logger.py`:
```python
import logging
import time

from fastapi import Request, Response

logger = logging.getLogger(__name__)

_EXCLUDE_PATHS = {"/metrics", "/api/v1/health"}


async def request_logging_middleware(request: Request, call_next):
    path = request.url.path
    if path in _EXCLUDE_PATHS:
        return await call_next(request)

    start = time.monotonic()
    response: Response = await call_next(request)
    elapsed = (time.monotonic() - start) * 1000

    extra = {
        "method": request.method,
        "path": path,
        "status": response.status_code,
        "duration_ms": round(elapsed, 1),
        "client_ip": request.client.host if request.client else None,
        "user_agent": request.headers.get("user-agent", ""),
    }

    log_fn = logger.warning if elapsed > 1000 else logger.info
    log_fn("%s %s -> %d (%.0fms)", request.method, path, response.status_code, elapsed, extra=extra)
    return response
```

Wait, the standard `logging.Logger` methods don't accept `extra=` as keyword directly to `warning()` / `info()`. The `extra` parameter goes to `LogRecord`. Let me fix:

```python
import logging
import time

from fastapi import Request, Response

logger = logging.getLogger(__name__)

_EXCLUDE_PATHS = {"/metrics", "/api/v1/health"}


async def request_logging_middleware(request: Request, call_next):
    path = request.url.path
    if path in _EXCLUDE_PATHS:
        return await call_next(request)

    start = time.monotonic()
    response: Response = await call_next(request)
    elapsed = (time.monotonic() - start) * 1000

    extra = {
        "method": request.method,
        "path": path,
        "status": response.status_code,
        "duration_ms": round(elapsed, 1),
        "client_ip": request.client.host if request.client else None,
        "user_agent": request.headers.get("user-agent", ""),
    }

    if elapsed > 1000:
        logger.warning("Slow request: %s %s -> %d (%.0fms)", request.method, path, response.status_code, elapsed, extra=extra)
    else:
        logger.info("%s %s -> %d (%.0fms)", request.method, path, response.status_code, elapsed, extra=extra)
    return response
```

Actually, `extra` is a valid parameter for `logging.Logger._log` but not directly for `info()`. The standard way is:

```python
logger.info("%s %s -> %d (%.0fms)", method, path, status, elapsed, extra={"key": "val"})
```

Wait, actually `extra` IS a valid keyword argument for `logging.Logger.info()`. From Python docs: "The second keyword argument is extra which can be used to pass a dictionary which is used to populate the __dict__ of the LogRecord created for the logging event."

Yes, this works. Let me use the `log_with_fields` helper from structured_log.py instead, to be consistent.

Actually let me simplify and just use `logging.Logger._log` or the `extra` parameter directly, since `log_with_fields` would require importing from structured_log.

Actually, looking at the `log_with_fields` function in structured_log.py:
```python
def log_with_fields(logger: logging.Logger, level: int, message: str, **fields) -> None:
    if logger.isEnabledFor(level):
        record = logger.makeRecord(...)
        record.extra_fields = fields
        logger.handle(record)
```

But wait - the `extra_fields` attribute on the record is checked in `JSONFormatter.format()`:
```python
if hasattr(record, "extra_fields"):
    entry.update(record.extra_fields)
```

So if we use `log_with_fields`, the extra fields will appear in JSON output. But if we use `logger.info(..., extra={...})`, the JSONFormatter won't pick them up because it looks for `extra_fields` attribute.

I should either:
1. Use `log_with_fields` for consistency with JSON output
2. Or update JSONFormatter to also check `record.__dict__` for extra fields added via `extra=`

Since the logger middleware is new code and we want consistency, let me use `log_with_fields` and also update JSONFormatter to handle `extra=` parameter for future use.

Let me write:

```python
import logging
import time

from fastapi import Request, Response

from src.monitoring.structured_log import log_with_fields

logger = logging.getLogger(__name__)

_EXCLUDE_PATHS = {"/metrics", "/api/v1/health"}


async def request_logging_middleware(request: Request, call_next):
    path = request.url.path
    if path in _EXCLUDE_PATHS:
        return await call_next(request)

    start = time.monotonic()
    response: Response = await call_next(request)
    elapsed = (time.monotonic() - start) * 1000

    fields = {
        "method": request.method,
        "path": path,
        "status": response.status_code,
        "duration_ms": round(elapsed, 1),
    }
    if request.client:
        fields["client_ip"] = request.client.host
    ua = request.headers.get("user-agent", "")
    if ua:
        fields["user_agent"] = ua

    level = logging.WARNING if elapsed > 1000 else logging.INFO
    log_with_fields(logger, level, "%s %s -> %d (%.0fms)" % (request.method, path, response.status_code, elapsed), **fields)
    return response
```

- [ ] **Step 2: Register request logging middleware in app.py**

In `src/api/app.py`, add after the metrics middleware registration (between metrics_middleware and auth_middleware):

```python
from src.monitoring.request_logger import request_logging_middleware

# ...in the middleware section after metrics_middleware...
app.add_middleware(request_logging_middleware.__class__)  # This won't work for function middleware
```

Wait, function middleware can't be added via `app.add_middleware`. We need to use `@app.middleware("http")` decorator. But we already have a metrics_middleware as a decorator function. Let me restructure the middleware section.

Actually, the cleanest approach: keep both `@app.middleware("http")` decorators in app.py, stacking them. FastAPI applies them in reverse order of decorator, so the top one runs first on requests (outermost).

Let me restructure. In app.py, after CORS middleware, I'll have:

```python
# Metrics + request logging middleware (stacked)
from src.monitoring.request_logger import request_logging_middleware as _req_log

@app.middleware("http")
async def _combined_monitoring(request: Request, call_next):
    # metrics first, then logging
    import time
    from src.monitoring.metrics import request_latency, request_total

    start = time.monotonic()
    response = await call_next(request)
    elapsed = time.monotonic() - start

    # Track metrics
    request_total.labels(method=request.method, path=request.url.path, status=response.status_code).inc()
    request_latency.labels(method=request.method, path=request.url.path).observe(elapsed)

    # Log request (excluding noise paths)
    path = request.url.path
    if path not in {"/metrics", "/api/v1/health"}:
        from src.monitoring.structured_log import log_with_fields
        fields = {
            "method": request.method,
            "path": path,
            "status": response.status_code,
            "duration_ms": round(elapsed * 1000, 1),
        }
        if request.client:
            fields["client_ip"] = request.client.host
        ua = request.headers.get("user-agent", "")
        if ua:
            fields["user_agent"] = ua
        level = logging.WARNING if elapsed > 1.0 else logging.INFO
        log_with_fields(logger, level, "%s %s -> %d (%.1fms)" % (request.method, path, response.status_code, elapsed * 1000), **fields)

    return response
```

Wait, this is getting complicated. The approach from the spec says to create the request logger as a new file. Let me just do it that way and register it.

But the problem is: how to register a function middleware from an external module?

Option A: `app.middleware` decorator inline in app.py
Option B: Use `app.add_middleware` with a class-based ASGI middleware wrapper
Option C: Put both metrics and logging into a single middleware, keep it in app.py

I'll go with a class-based ASGI middleware that combines metrics + request logging. This can be in the request_logger.py module and registered with `app.add_middleware`.

Actually, let me keep it simple. I'll modify metrics.py to convert the middleware into a class-based ASGI middleware, then add request logging there. No, that mixes concerns.

Simplest approach: create the middleware as a class in request_logger.py, register it via `app.add_middleware`.

Let me write it properly:

```python
# src/monitoring/request_logger.py
import logging
import time

from starlette.types import ASGIApp, Receive, Scope, Send

logger = logging.getLogger(__name__)

_EXCLUDE_PATHS = {"/metrics", "/api/v1/health"}


class RequestLoggingMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if path in _EXCLUDE_PATHS:
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "GET")
        start = time.monotonic()
        status = [200]

        async def wrapped_send(message: dict) -> None:
            if message["type"] == "http.response.start":
                status[0] = message.get("status", 200)
            await send(message)

        try:
            await self.app(scope, receive, wrapped_send)
        finally:
            elapsed = (time.monotonic() - start) * 1000
            extra = {
                "method": method,
                "path": path,
                "status": status[0],
                "duration_ms": round(elapsed, 1),
            }
            log_fn = logger.warning if elapsed > 1000 else logger.info
            log_fn("%s %s -> %d (%.0fms)", method, path, status[0], elapsed, extra=extra)
```

Wait, but `extra=` in `logger.info()` is a standard parameter. The JSONFormatter checks for `record.extra_fields` attribute, NOT the `extra` dict. The `extra` dict is merged into `record.__dict__`. So if we use `extra={...}`, those keys become available as attributes on the LogRecord.

Actually, Python's `logging.Logger.info()` does accept `extra` as a keyword argument. Let me verify what happens:

```python
logger.info("message", extra={"key": "value"})
```

The `extra` dict's items are merged into `record.__dict__`. So `record.key = "value"`. But our JSONFormatter checks `hasattr(record, "extra_fields")` which would NOT be set by `extra=`. 

So I should either:
1. Update JSONFormatter to merge all non-standard record attributes
2. Or use the structured_log's `log_with_fields` helper

Let me update JSONFormatter to merge all non-standard extra fields from the LogRecord. The standard attributes are well-known (name, levelno, levelname, pathname, filename, module, lineno, funcName, created, asctime, msecs, relativeCreated, exc_info, exc_text, stack_info, msg, args, process, processName, thread, threadName).

Simpler approach: use `log_with_fields`:

```python
from src.monitoring.structured_log import log_with_fields

# ...
fields = {
    "method": method,
    "path": path,
    "status": status[0],
    "duration_ms": round(elapsed, 1),
}
log_with_fields(logger, level, f"{method} {path} -> {status[0]} ({elapsed:.0f}ms)", **fields)
```

Wait but `log_with_fields` constructs a new LogRecord manually, which means it creates a record that skips stack inspection (no correct lineno/funcName). That's fine for this use case, but let me check if we should improve it.

The current `log_with_fields` does:
```python
record = logger.makeRecord(logger.name, level, "", 0, message, (), None)
record.extra_fields = fields
logger.handle(record)
```

The `makeRecord` params are: `(name, level, fn, lno, msg, args, exc_info, func=None, extra=None, sinfo=None)`. So fn="", lno=0 means we lose the caller location. We could improve this using `sys._getframe()` but that's fragile.

For middleware logs, the caller location (request_logger.py line XX) is actually correct and useful. So let's just use normal logging but update JSONFormatter.

The cleanest fix: update `JSONFormatter.format()` to capture all record attributes beyond the standard ones.

Let me finalize:

For `request_logger.py` - use the standard `logging.Logger.info()` with `extra=` parameter. Then update JSONFormatter to capture all attributes added via `extra={}`.

Standard LogRecord attributes to exclude from extra capture:
`args`, `asctime`, `created`, `exc_info`, `exc_text`, `filename`, `funcName`, `levelname`, `levelno`, `lineno`, `module`, `msecs`, `msg`, `name`, `pathname`, `process`, `processName`, `relativeCreated`, `stack_info`, `thread`, `threadName`

Actually, the simplest approach is just to use `log_with_fields` which we've already established works correctly. Let me keep it simple.

OK, let me just write the final version with `log_with_fields`:

```python
import logging
import time

from starlette.types import ASGIApp, Receive, Scope, Send

from src.monitoring.structured_log import log_with_fields

logger = logging.getLogger(__name__)

_EXCLUDE_PATHS = {"/metrics", "/api/v1/health"}


class RequestLoggingMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if path in _EXCLUDE_PATHS:
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "GET")
        start = time.monotonic()
        status = [200]

        async def wrapped_send(message: dict) -> None:
            if message["type"] == "http.response.start":
                status[0] = message.get("status", 200)
            await send(message)

        try:
            await self.app(scope, receive, wrapped_send)
        finally:
            elapsed = (time.monotonic() - start) * 1000
            fields = {
                "method": method,
                "path": path,
                "status": status[0],
                "duration_ms": round(elapsed, 1),
                "component": "request_logger",
            }
            if elapsed > 1000:
                log_with_fields(logger, logging.WARNING, f"SLOW {method} {path} -> {status[0]} ({elapsed:.0f}ms)", **fields)
            else:
                log_with_fields(logger, logging.INFO, f"{method} {path} -> {status[0]} ({elapsed:.0f}ms)", **fields)
```

And register in `app.py`:
```python
from src.monitoring.request_logger import RequestLoggingMiddleware
app.add_middleware(RequestLoggingMiddleware)
```

This goes after the metrics middleware but before auth middleware.

- [ ] **Step 3: Run tests**

```bash
cd D:\projects\AIMiddlePlatform
uv run pytest tests/ -v --tb=short 2>&1
```
Expected: All tests pass.

- [ ] **Step 4: Commit**

```bash
cd D:\projects\AIMiddlePlatform
git add src/monitoring/request_logger.py src/api/app.py
git commit -m "feat: add request logging middleware

RequestLoggingMiddleware logs each HTTP request with method, path,
status code, duration, and client IP. Uses JSON format via
log_with_fields. Skips /metrics and /health to reduce noise.
Slow requests (>1s) logged at WARNING level.
"
```

---

## Task 5: Worker Monitoring Enhancement

**Files:**
- Modify: `src/worker.py`
- Modify: `pyproject.toml` (if adding metrics endpoint dependency - not needed, prometheus_client already there)

- [ ] **Step 1: Add JSON logging to worker**

Edit `src/worker.py`:

Add import at top:
```python
from src.monitoring.structured_log import setup_json_logging
```

Replace `logging.basicConfig(level=logging.INFO)` at line 269 with:
```python
    setup_json_logging()
    asyncio.run(run_worker())
```

- [ ] **Step 2: Add Prometheus metrics endpoint to worker**

Add a simple HTTP server for Prometheus metrics in the worker. Add at the end of `run_worker()` or create a startup helper.

Edit `src/worker.py`:
```python
def _start_metrics_server(port: int = 8200) -> None:
    from prometheus_client import start_http_server
    try:
        start_http_server(port)
        logger.info("Worker metrics server started on port %d", port)
    except Exception as e:
        logger.warning("Failed to start worker metrics server: %s", e)
```

Add worker-specific metrics at module level:
```python
from prometheus_client import Counter, Histogram

worker_tasks_total = Counter(
    "worker_tasks_total",
    "Total tasks processed by worker",
    labelnames=["status"],
)

worker_tasks_latency = Histogram(
    "worker_tasks_latency_seconds",
    "Worker task processing latency",
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)
```

Record metrics in `process_one()`:
```python
async def process_one(self, message: dict) -> dict:
    task_id = message.get("task_id", "unknown")
    camera_id = message.get("camera_id", "unknown")
    start = asyncio.get_event_loop().time()
    # ... existing code ...
    try:
        result = await self.fast_path.process(message)
        # ... rest of existing code ...
        elapsed = asyncio.get_event_loop().time() - start
        worker_tasks_total.labels(status="success").inc()
        worker_tasks_latency.observe(elapsed)
        # ... existing result handling ...
    except Exception as e:
        worker_tasks_total.labels(status="error").inc()
        raise
```

Wait, the current process_one() doesn't catch exceptions broadly. Let me be more careful with the edit.

Actually, looking at the existing code, process_one doesn't have a try/except around the processing except for the cache push. Let me add metrics while keeping the same flow:

In `run_worker()`:
```python
async def run_worker(db_url: str = "sqlite+aiosqlite:///data/aimp.db"):
    _start_metrics_server()
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
```

And in `process_one`, record metrics:
```python
async def process_one(self, message: dict) -> dict:
    ...
    start = asyncio.get_event_loop().time()
    frame_raw = message.get("frame", "")
    image = _decode_frame(frame_raw) if frame_raw else None

    result = await self.fast_path.process(message)

    latency = (asyncio.get_event_loop().time() - start) * 1000
    worker_tasks_total.labels(status="success" if result is not None else "error").inc()
    worker_tasks_latency.observe(latency / 1000)
    ...
```

Let me write the full edits more carefully after reading the file.

- [ ] **Step 3: Run tests**

```bash
cd D:\projects\AIMiddlePlatform
uv run pytest tests/ -v --tb=short 2>&1
```
Expected: All tests pass.

- [ ] **Step 4: Commit**

```bash
cd D:\projects\AIMiddlePlatform
git add src/worker.py
git commit -m "feat: worker monitoring - JSON logging and Prometheus metrics

Worker now uses JSON structured logging instead of basicConfig.
Starts a Prometheus HTTP metrics server on port 8200 with
worker_tasks_total and worker_tasks_latency_seconds metrics.
"
```

---

## Task 6: Fix Helm Chart Paths

**Files:**
- Modify: `deploy/helm/aimp/templates/servicemonitor.yaml`
- Modify: `deploy/helm/aimp/values.yaml` (check if metrics section needs updates)

- [ ] **Step 1: Read dependency.yaml (not deployment-api.yaml - that path is already correct)**

Check `deploy/helm/aimp/templates/deployment-api.yaml` line 82-89 - already uses `/api/v1/health`. Verify with:
```bash
cd D:\projects\AIMiddlePlatform
Select-String "health" deploy/helm/aimp/templates/deployment-api.yaml
```
Expected: Already shows `/api/v1/health`.

- [ ] **Step 2: Fix ServiceMonitor path**

Edit `deploy/helm/aimp/templates/servicemonitor.yaml` line 16:
Change `path: /api/v1/metrics` to `path: /metrics`.

- [ ] **Step 3: Verify paths with helm lint**

```bash
cd D:\projects\AIMiddlePlatform
helm lint deploy/helm/aimp/
```
Expected: Chart passes lint.

- [ ] **Step 4: Commit**

```bash
cd D:\projects\AIMiddlePlatform
git add deploy/helm/aimp/templates/servicemonitor.yaml
git commit -m "fix: correct ServiceMonitor metrics path

ServiceMonitor was pointing to /api/v1/metrics but the actual
endpoint is /metrics.
"
```

---

## Task 7: Grafana Dashboard JSON

**Files:**
- Create: `deploy/grafana/dashboards/aimp-core-metrics.json`

- [ ] **Step 1: Create directory**

```bash
cd D:\projects\AIMiddlePlatform
New-Item -ItemType Directory -Path deploy/grafana/dashboards -Force
```

- [ ] **Step 2: Create Grafana dashboard JSON**

Write `deploy/grafana/dashboards/aimp-core-metrics.json` with the following panels sourced from the Prometheus metrics defined in `src/monitoring/metrics.py`:

The dashboard JSON is large (typically 300-500 lines). Key panels:
1. **QPS** - `rate(app_requests_total[1m])` - stat panel
2. **Request Latency (P50/P95/P99)** - histogram_quantile on `app_request_latency_seconds_bucket`
3. **DAG Execution Rate** - `rate(dag_execution_total[1m])` by status
4. **Model Inference Rate** - `rate(model_inference_total[1m])` by status
5. **Path Distribution** - `rate(path_decision_total[1m])` by path
6. **Active Streams** - `active_streams` gauge
7. **Health Status** - text panel from health endpoint

Generate a valid Grafana 8+ dashboard JSON. Use uid `aimp-core-metrics`, title `AIMP Core Metrics`.

```json
{
  "title": "AIMP Core Metrics",
  "uid": "aimp-core-metrics",
  ...
}
```

(Full JSON will be written in implementation - ~400 lines with 6-7 panels)

- [ ] **Step 3: Commit**

```bash
cd D:\projects\AIMiddlePlatform
git add deploy/grafana/dashboards/aimp-core-metrics.json
git commit -m "feat: add Grafana core metrics dashboard JSON

Dashboard with panels for QPS, latency percentiles, DAG execution,
model inference, path distribution, active streams, and health status.
Importable JSON for Grafana 8+.
"
```

---

## Task 8: PrometheusRule CRD

**Files:**
- Create: `deploy/helm/aimp/templates/prometheusrule.yaml`

- [ ] **Step 1: Create PrometheusRule template**

Create `deploy/helm/aimp/templates/prometheusrule.yaml`:
```yaml
{{- if .Values.metrics.prometheusRule.enabled }}
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: {{ include "aimp.fullname" . }}
  labels:
    {{- include "aimp.labels" . | nindent 4 }}
spec:
  groups:
    - name: aimp-alerts
      interval: 30s
      rules:
        - alert: HighErrorRate
          expr: rate(app_requests_total{status=~"5.."}[5m]) > 0.05
          for: 5m
          labels:
            severity: critical
          annotations:
            summary: "High HTTP error rate ({{ "{{ $value | humanizePercentage }}" }})"
            description: "More than 5% of requests are returning 5xx errors"

        - alert: HighLatency
          expr: histogram_quantile(0.99, rate(app_request_latency_seconds_bucket[5m])) > 5
          for: 5m
          labels:
            severity: warning
          annotations:
            summary: "High request latency (P99 > 5s)"
            description: "P99 latency is {{ "{{ $value | humanizeDuration }}" }}"

        - alert: StreamDisconnect
          expr: rate(stream_disconnect_total[5m]) > 10
          for: 2m
          labels:
            severity: warning
          annotations:
            summary: "High stream disconnect rate"
            description: "More than 10 streams disconnecting per minute"

        - alert: LowThroughput
          expr: rate(app_requests_total[5m]) < 50
          for: 10m
          labels:
            severity: info
          annotations:
            summary: "Low request throughput"
            description: "Request rate dropped below 50 req/min"

        - alert: WorkerDown
          expr: up{job="aimp-worker"} == 0
          for: 1m
          labels:
            severity: critical
          annotations:
            summary: "Worker process is down"
            description: "Worker has been unreachable for more than 1 minute"
{{- end }}
```

- [ ] **Step 2: Add prometheusRule config to values.yaml**

Edit `deploy/helm/aimp/values.yaml` to add:
```yaml
metrics:
  enabled: false
  serviceMonitor:
    enabled: false
    namespace: monitoring
    interval: 30s
  prometheusRule:
    enabled: false
```

Check if `metrics.enabled` and `metrics.serviceMonitor` already exist in values.yaml first.

- [ ] **Step 3: Validate helm template**

```bash
cd D:\projects\AIMiddlePlatform
helm lint deploy/helm/aimp/
```
Expected: Chart passes lint.

- [ ] **Step 4: Commit**

```bash
cd D:\projects\AIMiddlePlatform
git add deploy/helm/aimp/templates/prometheusrule.yaml deploy/helm/aimp/values.yaml
git commit -m "feat: add PrometheusRule CRD with alerting rules

Adds alerting rules for: high error rate (>5% 5xx), high latency
(P99 >5s), stream disconnects (>10/min), low throughput (<50 req/min),
and worker down. Disabled by default via .Values.metrics.prometheusRule.enabled.
"
```

---

## Task 9: Apply trace_async Decorator

**Files:**
- Modify: `src/pipeline/executor.py`
- Modify: `src/models/inference.py`
- Modify: `src/agent/orchestrator.py`

- [ ] **Step 1: Add @trace_async to executor.py**

Edit `src/pipeline/executor.py`:

Add import at top:
```python
from src.monitoring.tracing import trace_async
```

Apply to `execute()` method:
```python
    @trace_async(span_name="dag.execute", attributes={"component": "executor"})
    async def execute(self, dag: DAGDefinition, context: dict[str, Any]) -> dict[str, Any]:
```

- [ ] **Step 2: Add @trace_async to inference.py**

Edit `src/models/inference.py`:

Add import:
```python
from src.monitoring.tracing import trace_async
```

Apply to `infer()` method:
```python
    @trace_async(span_name="model.infer", attributes={"component": "inference"})
    async def infer(self, model_id: str, input_data: Any) -> dict[str, Any]:
```

- [ ] **Step 3: Add @trace_async to orchestrator.py**

Edit `src/agent/orchestrator.py`:

Add import:
```python
from src.monitoring.tracing import trace_async
```

Apply to `process()` method:
```python
    @trace_async(span_name="agent.process", attributes={"component": "orchestrator"})
    async def process(self, frame_context: dict[str, Any], image_data: bytes | None = None) -> dict[str, Any]:
```

- [ ] **Step 4: Run tests to verify**

```bash
cd D:\projects\AIMiddlePlatform
uv run pytest tests/ -v --tb=short 2>&1
```
Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
cd D:\projects\AIMiddlePlatform
git add src/pipeline/executor.py src/models/inference.py src/agent/orchestrator.py
git commit -m "feat: apply trace_async decorator to key functions

Adds OpenTelemetry tracing spans to:
- DAGExecutor.execute() as 'dag.execute'
- InferenceOrchestrator.infer() as 'model.infer'
- AgentOrchestrator.process() as 'agent.process'
"
```

---

## Verification

After all tasks complete, run:

```bash
cd D:\projects\AIMiddlePlatform
uv run pytest tests/ -v --tb=short 2>&1
```

Expected: All tests pass (existing count ~317 collected, 307 passed, 2 skipped).
