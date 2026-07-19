# Monitoring & Observability Enhancement Design

## Overview

Enhance the existing monitoring infrastructure in AIMiddlePlatform by fixing broken components and adding basic observability features including structured logging, request metrics, enhanced health checks, Grafana dashboards, Prometheus alerting rules, and Worker monitoring.

## Scope

**Fix 4 existing issues:**
1. Register `metrics_middleware` which is defined but never attached to the FastAPI app
2. Activate JSON structured logging (`setup_json_logging()` never called at startup)
3. Fix K8s deployment health probe path (`/health` → `/api/v1/health`)
4. Fix Prometheus ServiceMonitor path (`/api/v1/metrics` → `/metrics`)

**Add 6 enhancements:**
1. Enhanced health check endpoint with dependency liveness probes
2. Structured request logging middleware
3. Worker process monitoring (JSON logging + metrics endpoint)
4. Grafana core metrics dashboard (JSON provisioning file)
5. PrometheusRule CRD with alerting rules
6. Apply `trace_async` decorator to key async functions

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│                      FastAPI App                          │
│  Middleware Stack (order):                                │
│    CORS → MetricsMiddleware (fixed) → RequestLogMiddleware│
│                                        (new) → Auth       │
│                                                           │
│  Endpoints:                                                │
│    GET /api/v1/health  (enhanced with dependency checks)   │
│    GET /metrics        (Prometheus, existing)              │
│    GET /api/v1/logs    (existing)                          │
│    GET /api/v1/traces  (existing)                          │
│                                                           │
│  Lifespan:                                                 │
│    setup_json_logging()  (new call)                        │
│    init_log_buffer()     (existing)                        │
│    init_tracing()        (existing)                        │
└──────────────────────────────────┬───────────────────────┘
                                   │
┌──────────────────────────────────▼───────────────────────┐
│  Worker Process (separate)                                │
│    setup_json_logging()  (new)                            │
│    /metrics HTTP endpoint (new)                           │
│    trace_async on key fns (new)                           │
└──────────────────────────────────┬───────────────────────┘
                                   │
                                   ▼
┌──────────────────────────────────────────────────────────┐
│  Prometheus (collects from both API + Worker)             │
│  ServiceMonitor → fixed to /metrics path                 │
│  PrometheusRule → alerting rules (new)                   │
└──────────────────────────────────┬───────────────────────┘
                                   │
                                   ▼
┌──────────────────────────────────────────────────────────┐
│  Grafana Dashboard (import JSON)                         │
│  aimp-core-metrics.json (new)                            │
└──────────────────────────────────────────────────────────┘
```

## Detailed Design

### Fix 1: Register metrics_middleware

**File:** `src/api/app.py`

The `metrics_middleware` ASGI middleware defined in `src/monitoring/metrics.py` tracks `app_requests_total` and `app_request_latency_seconds` per request. It must be registered before the auth middleware to capture all requests including auth failures.

Implementation: use `@app.middleware("http")` decorator pattern (FastAPI standard for function-based middleware), registered between CORS and auth middleware in the wrapper order.

### Fix 2: Activate JSON Logging

**File:** `src/api/app.py`

```python
# In lifespan startup, before other init
from src.monitoring.structured_log import setup_json_logging
setup_json_logging()
```

This replaces the root logger's handler with a JSON-formatted stdout handler.

**File:** `src/monitoring/structured_log.py`

Need to ensure `setup_json_logging()` is idempotent (safe to call multiple times) and preserves existing log levels.

### Fix 3: K8s Health Probe Path

**File:** `deploy/helm/aimp/templates/deployment-api.yaml`

Change:
- `livenessProbe.httpGet.path: /health` → `/api/v1/health`
- `readinessProbe.httpGet.path: /health` → `/api/v1/health`

### Fix 4: ServiceMonitor Path

**File:** `deploy/helm/aimp/templates/servicemonitor.yaml`

Change:
- `endpoints[0].path: /api/v1/metrics` → `/metrics`

### Enhancement 1: Enhanced Health Check

**File:** `src/api/routes/health.py`

Replace static response with dependency checks:

| Check | Method | Failure handling |
|-------|--------|-----------------|
| Database | Execute `SELECT 1` with timeout | degraded if fail |
| Redis | `PING` with timeout | degraded if fail |
| LLM | Check `LLMHealthChecker.available` | degraded if unavailable |
| Model Registry | Check model count > 0 | degraded if empty |

Response format:
```json
{
  "status": "ok" | "degraded" | "error",
  "service": "aimiddleplatform",
  "version": "0.1.0",
  "uptime_seconds": 3600,
  "checks": {
    "database": { "status": "ok", "latency_ms": 2 },
    "redis": { "status": "ok", "latency_ms": 1 },
    "llm": { "status": "ok", "available": true },
    "model_registry": { "status": "ok", "models_count": 12 }
  }
}
```

Status logic:
- All ok → `"ok"`
- Any degraded, none error → `"degraded"`
- Any error → `"error"`

### Enhancement 2: Request Logging Middleware

**File:** `src/monitoring/request_logger.py` (new)

ASGI middleware that logs every request with:
- `method`, `path`, `status_code`, `duration_ms`
- `client_ip`, `user_agent`
- `trace_id` (from OpenTelemetry if available)

Slow requests (>1s) logged at WARNING, others at INFO.

Excluded paths: `/metrics`, `/api/v1/health` (to avoid noise).

### Enhancement 3: Worker Monitoring

**Files:**
- `src/worker.py`: Add `setup_json_logging()` at startup
- `src/worker.py`: Start a simple Prometheus HTTP server on a configurable port (default `8200`) exposing worker metrics
- Add worker-specific metrics: `worker_tasks_total`, `worker_tasks_latency_seconds`, `worker_errors_total`

### Enhancement 4: Grafana Dashboard JSON

**File:** `deploy/grafana/dashboards/aimp-core-metrics.json`

Dashboard panels:
1. **QPS** — Rate of `app_requests_total[1m]`
2. **Request Latency (P50/P95/P99)** — `app_request_latency_seconds` histogram quantiles
3. **DAG Execution** — `dag_execution_total` rate by status + `dag_execution_latency_seconds` heatmap
4. **Model Inference** — `model_inference_total` rate by status + latency
5. **Path Distribution** — Fast vs Agent path split from `path_decision_total`
6. **Active Streams** — `active_streams` gauge
7. **Health Status** — health check endpoint status from up/down scraper

### Enhancement 5: PrometheusRule CRD

**File:** `deploy/helm/aimp/templates/prometheusrule.yaml`

Rules:
| Rule | Expression | Severity | Duration |
|------|-----------|----------|----------|
| HighErrorRate | `rate(app_requests_total{status=~"5.."}[5m]) > 0.05` | critical | 5m |
| HighLatency | `histogram_quantile(0.99, ...) > 5` | warning | 5m |
| StreamDisconnect | `rate(stream_disconnect_total[5m]) > 10` | warning | 2m |
| LowThroughput | `rate(app_requests_total[5m]) < 50` | info | 10m |

### Enhancement 6: trace_async Application

Apply `@trace_async` decorator to:
- `src/pipeline/executor.py`: `execute_dag()` method
- `src/models/inference.py`: `predict()` method
- `src/agent/orchestrator.py`: `process()` method

## Files Changed/Added

| File | Action | Description |
|------|--------|-------------|
| `src/api/app.py` | Edit | Register metrics_middleware, call setup_json_logging |
| `src/monitoring/structured_log.py` | Edit | Make setup_json_logging idempotent |
| `src/api/routes/health.py` | Edit | Enhanced health check with dependency probes |
| `src/monitoring/request_logger.py` | **New** | Request logging ASGI middleware |
| `src/worker.py` | Edit | JSON logging, prometheus endpoint, trace_async |
| `deploy/helm/aimp/templates/deployment-api.yaml` | Edit | Fix health probe paths |
| `deploy/helm/aimp/templates/servicemonitor.yaml` | Edit | Fix metrics path |
| `deploy/grafana/dashboards/aimp-core-metrics.json` | **New** | Grafana dashboard JSON |
| `deploy/helm/aimp/templates/prometheusrule.yaml` | **New** | Prometheus alerting rules |
| `src/pipeline/executor.py` | Edit | Add `@trace_async` |
| `src/models/inference.py` | Edit | Add `@trace_async` |
| `src/agent/orchestrator.py` | Edit | Add `@trace_async` |

## Testing Strategy

- `metrics_middleware` registration: verify `/metrics` returns prometheus data including `app_requests_total` and `app_request_latency_seconds`
- JSON logging: verify stdout output is valid JSON with expected fields
- Health check: verify response includes all dependency checks, test degraded scenarios (mock failures)
- Request logging: verify middleware logs request entries at appropriate levels
- Worker monitoring: verify worker starts metrics server and JSON logging
- All existing monitoring tests continue to pass
- `trace_async`: verify spans are created for traced functions

## Dependencies

No new external dependencies. All functionality uses existing packages:
- `prometheus-client>=0.25.0` (already in pyproject.toml)
- `opentelemetry-*` (already in pyproject.toml)
- Python standard library `logging`
