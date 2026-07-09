# Management UI Design for AIMiddlePlatform

## Overview

A Vue 3 + Element Plus single-page application providing operational management for the CV algorithm scheduling platform. Three-phase delivery starting with the most impactful pages.

## Tech Stack

| Layer | Choice |
|-------|--------|
| Frontend | Vue 3 + Composition API + Vite |
| UI Components | Element Plus |
| State | Pinia |
| HTTP | Axios |
| Charts | ECharts (via vue-echarts) |
| Router | Vue Router 4 |
| Build | Vite |
| Auth | JWT (backend) + token stored in localStorage |

## Architecture

```
Browser (Vue SPA) ──HTTP JSON──> FastAPI Backend (:8000)
       │                              │
       │  /api/v1/*                    │  OpenAPI /docs for dev
       │  /ws/* (WebSocket)            │
       │                              └── Prometheus metrics
       │                              └── OpenTelemetry traces
       └── ECharts dashboards
```

The frontend is a standalone SPA communicating with the backend exclusively via REST JSON APIs. No server-side rendering.

**Serving strategy:**
- Development: Vite dev server with proxy to FastAPI (`:5173` → `:8000`)
- Production: Nginx container serving built static files, reverse-proxying `/api/` and `/v1/` to the FastAPI container

```
Browser ──:80──> Nginx
                  ├── /api/*  ──proxy──> FastAPI :8000
                  ├── /v1/*   ──proxy──> FastAPI :8000
                  └── /*      ──static─> index.html (SPA fallback)
```

## Phase 1 — Dashboard + Camera Management

### Pages

**1. System Dashboard (`/dashboard`)**
- Real-time QPS chart (line, last 5 min, 1s interval)
- P50 / P95 / P99 latency gauge
- Camera online/offline/total count
- Active model count
- Error rate (last 5 min)
- Top 5 slowest cameras

**2. Camera Management (`/cameras`)**
- Table: camera_id, stream_url, protocol (RTSP/GB28181), status (online/offline/error), FPS, last_active
- Create: modal form with stream_url, protocol, fps, roi
- Edit: same modal pre-filled
- Delete: confirm dialog
- Status badge: green (online) / red (offline) / yellow (error)

### Backend Changes Required

**New endpoints:**
- `GET /api/v1/system/stats` — aggregated dashboard stats (qps, latency, camera count, error rate)
- `GET /api/v1/system/stats/history?range=5m` — time-series data for charts

**Existing endpoints used:**
- `GET /v1/streams` — list cameras
- `POST /v1/analyze/stream` — register camera
- `GET /v1/tasks/{task_id}/results` — (for future use)

**Authentication (new):**
- `POST /api/v1/auth/login` — returns JWT
- `POST /api/v1/auth/refresh` — refresh token
- All `/api/v1/*` routes require `Authorization: Bearer <token>`

### Frontend Components

```
src/
  api/              # Axios instances + endpoint modules
    client.ts       # base axios, interceptors
    auth.ts         # login, refresh
    cameras.ts      # CRUD operations
    dashboard.ts    # stats endpoints
    models.ts       # model endpoints
    agent.ts        # agent config endpoints
  router/
    index.ts        # route definitions + guards
  stores/
    auth.ts         # user + token state
    dashboard.ts    # real-time stats
    cameras.ts      # camera list state
  views/
    Login.vue
    Layout.vue      # sidebar + topbar shell
    Dashboard.vue
    Cameras/
      Index.vue     # table
      FormDialog.vue # create/edit modal
  components/
    Sidebar.vue
    TopBar.vue
    StatCard.vue
    LineChart.vue
    StatusBadge.vue
```

## Phase 2 — Model Management + Agent Config

### Pages

**3. Model Management (`/models`)**
- Table: model_id, name, version, backend (onnx/triton), status (online/offline/deprecated), tags, description
- Filter by backend, status
- Status toggle (online ↔ offline)
- Detail view: inference latency chart (P50/P95 over last hour), request count, last error

**4. Agent Configuration (`/agent`)**
- LLM endpoint config: provider select (Qwen/DeepSeek), URL, API key (masked)
- System prompt editor (textarea with syntax highlight)
- Confidence thresholds: slider per scene type (parking_lot, entrance, street, etc.)
- Routing rules table: scene_id ↔ pipeline mapping, add/delete directly
- Config save button → calls `POST /v1/config/reload`

### Backend Changes Required

**New endpoints:**
- `GET /api/v1/models/{id}/stats` — per-model latency & request metrics
- `POST /api/v1/agent/config` — save agent-specific settings
- `GET /api/v1/agent/config` — load agent settings

**Existing endpoints used:**
- `GET /v1/models/`, `GET /v1/models/active`, `GET /v1/models/{id}`
- `POST /v1/models/{id}/status`
- `POST /v1/routing/routes`, `DELETE /v1/routing/routes/{scene_id}`
- `POST /v1/routing/matchers/camera_id`, `POST /v1/routing/matchers/scene_type`
- `GET /v1/config/`, `POST /v1/config/reload`

## Phase 3 — Pipeline Orchestration + Logs & Tracing

### Pages

**5. Pipeline Orchestration (`/pipelines`)**
- Pipeline list: name, node count, created_at
- Visual DAG editor: drag-and-drop nodes on canvas
  - Node types: MODEL_INFERENCE, CONDITION, AGGREGATE, OUTPUT
  - Each node has config panel (right sidebar): model_id, parameters
  - Connection lines between nodes (depends_on)
- Validate & Save → registers DAG in backend PipelineRegistry
- Delete pipeline

**6. Logs & Tracing (`/logs`, `/traces`)**
- Logs: search bar, level filter (INFO/WARN/ERROR), time range, module filter
  - Virtual-scroll table with expandable detail
- Traces: list of recent traces, filter by duration > X, error only
  - Trace detail: waterfall view of spans with timing

### Backend Changes Required

**New endpoints:**
- `GET/POST/PUT/DELETE /api/v1/pipelines` — DAG CRUD
- `GET /api/v1/pipelines/{name}/dag` — get full DAG definition
- `GET /api/v1/logs?level=&module=&time_range=&q=` — structured log query
- `GET /api/v1/traces?min_duration=&error_only=&limit=` — trace list
- `GET /api/v1/traces/{trace_id}` — full trace detail with spans

Note: Logs and traces require a storage backend (e.g., Loki for logs, Jaeger for traces). The current OpenTelemetry instrumentation exports to stdout only. This phase may need infrastructure changes.

## Authentication & Authorization

Simple JWT-based auth for the management UI:

- Default admin credentials seeded on first startup
- JWT expiry: 24h, refresh token: 7d
- Admin routes (`/api/v1/*`) behind auth middleware
- Existing pipeline routes (`/v1/*`) remain unauth in Phase 1; auth can be added in a later hardening pass
- Public routes: `/health`, `/metrics`, `/docs`, `/api/v1/auth/login`

## Directory Structure

```
aimiddleplatform/
  src/
    api/
      routes/
        admin/          # new: /api/v1/* endpoints
          auth.py
          dashboard.py
          logs.py
          pipelines.py
    frontend/           # new: Vue 3 SPA
      package.json
      vite.config.ts
      index.html
      src/
        main.ts
        App.vue
        api/
        router/
        stores/
        views/
        components/
  docker-compose.yml    # add nginx or serve static from FastAPI
```

## Delivery Order

```
Phase 1 (current)
  ├── Backend: auth + system stats endpoints
  ├── Frontend: project scaffold, Login, Layout, Sidebar
  ├── Frontend: Dashboard page (charts + stats)
  └── Frontend: Camera Management page (table + CRUD)

Phase 2
  ├── Backend: model stats + agent config endpoints
  ├── Frontend: Model Management page
  └── Frontend: Agent Configuration page

Phase 3
  ├── Backend: DAG CRUD + log/trace query endpoints
  ├── Infrastructure: Loki/Jaeger deployment
  ├── Frontend: Pipeline Orchestration (DAG editor)
  └── Frontend: Logs & Tracing pages
```
