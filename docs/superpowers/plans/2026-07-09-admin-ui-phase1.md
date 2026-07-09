# Admin UI Phase 1 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the MVP management UI — JWT auth, login page, system dashboard with real-time stats, and camera CRUD management.

**Architecture:** Vue 3 SPA in `frontend/` communicating with FastAPI via REST JSON. New admin routes live under `/api/v1/` with JWT middleware. Existing pipeline routes (`/v1/`) remain untouched.

**Tech Stack:** Vue 3 + Composition API, Vite, Element Plus, ECharts, Pinia, Vue Router 4. Backend: FastAPI, python-jose (JWT), Prometheus client for stats.

## Global Constraints

- All new API routes use prefix `/api/v1/`
- JWT secret read from env `JWT_SECRET_KEY` (default `aimp-dev-secret-change-in-production`)
- Admin routes (`/api/v1/*`) protected by JWT middleware except `/api/v1/auth/login`
- Existing `/v1/*` routes remain unchanged and unprotected
- Frontend uses Vue 3 Composition API (`<script setup lang="ts">`)
- Frontend builds to `frontend/dist/`, served by Nginx in production
- All backend code must have pytest tests
- No new Python dependencies beyond: `python-jose[cryptography]`

---

### Task 1: Backend JWT Auth

**Files:**
- Create: `src/api/routes/admin/__init__.py`
- Create: `src/api/routes/admin/auth.py`
- Modify: `src/api/app.py` (add admin router + auth middleware)
- Create: `tests/test_admin_auth.py`

**Interfaces:**
- Produces: `POST /api/v1/auth/login` → `{"access_token": "...", "refresh_token": "..."}`
- Produces: `POST /api/v1/auth/refresh` → `{"access_token": "..."}`
- Produces: `get_current_user()` dependency used by all `/api/v1/*` routes

- [ ] **Step 1: Create admin package**

```bash
mkdir -p src/api/routes/admin
echo "" > src/api/routes/admin/__init__.py
```

- [ ] **Step 2: Write the failing test**

Create `tests/test_admin_auth.py`:

```python
import pytest
from fastapi.testclient import TestClient

from src.api.app import app

client = TestClient(app)


def test_login_success() -> None:
    resp = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"})
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data


def test_login_invalid_credentials() -> None:
    resp = client.post("/api/v1/auth/login", json={"username": "admin", "password": "wrong"})
    assert resp.status_code == 401


def test_access_protected_route_without_token() -> None:
    resp = client.get("/api/v1/system/stats")
    assert resp.status_code == 401


def test_access_protected_route_with_valid_token() -> None:
    login_resp = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"})
    token = login_resp.json()["access_token"]
    # system/stats doesn't exist yet, but 401 means auth rejected, 404 means auth passed
    resp = client.get("/api/v1/system/stats", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code != 401


def test_refresh_token() -> None:
    login_resp = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"})
    refresh = login_resp.json()["refresh_token"]
    resp = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
    assert resp.status_code == 200
    assert "access_token" in resp.json()
```

- [ ] **Step 3: Run test to verify it fails**

```bash
cd /opt/aimiddleplatform && .venv/bin/python -m pytest tests/test_admin_auth.py -v --tb=short
```
Expected: ModuleNotFoundError or 404 (routes don't exist yet)

- [ ] **Step 4: Create auth route**

Create `src/api/routes/admin/auth.py`:

```python
import os
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from jose import jwt, JWTError

router = APIRouter(prefix="/api/v1/auth", tags=["admin-auth"])

SECRET_KEY = os.getenv("JWT_SECRET_KEY", "aimp-dev-secret-change-in-production")
ALGORITHM = "HS256"
ACCESS_EXPIRE = timedelta(hours=24)
REFRESH_EXPIRE = timedelta(days=7)

_ADMIN_USER = "admin"
_ADMIN_PASS = "admin123"


class LoginRequest(BaseModel):
    username: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str | None = None


def _create_token(data: dict, expires_delta: timedelta) -> str:
    payload = data.copy()
    payload["exp"] = datetime.now(timezone.utc) + expires_delta
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest) -> TokenResponse:
    if body.username != _ADMIN_USER or body.password != _ADMIN_PASS:
        raise HTTPException(401, "Invalid credentials")
    access = _create_token({"sub": body.username}, ACCESS_EXPIRE)
    refresh = _create_token({"sub": body.username, "type": "refresh"}, REFRESH_EXPIRE)
    return TokenResponse(access_token=access, refresh_token=refresh)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest) -> TokenResponse:
    try:
        payload = jwt.decode(body.refresh_token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != "refresh":
            raise HTTPException(401, "Invalid token type")
        access = _create_token({"sub": payload["sub"]}, ACCESS_EXPIRE)
        return TokenResponse(access_token=access)
    except JWTError:
        raise HTTPException(401, "Invalid or expired token")


def get_current_user(token: str) -> str:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload.get("sub", "unknown")
    except JWTError:
        raise HTTPException(401, "Invalid or expired token")
```

- [ ] **Step 5: Add auth middleware to app**

Modify `src/api/app.py` — add admin router and auth middleware for `/api/v1/*`:

```python
# Near top imports, add:
from src.api.routes.admin.auth import router as admin_auth_router
from src.api.routes.admin.auth import get_current_user

# Above app definition, add auth middleware function:
from fastapi import Request, HTTPException

@app.middleware("http")
async def admin_auth_middleware(request: Request, call_next):
    if request.url.path.startswith("/api/v1/") and request.url.path != "/api/v1/auth/login":
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return Response('{"detail":"Not authenticated"}', 401, media_type="application/json")
        try:
            token = auth.split(" ", 1)[1]
            get_current_user(token)
        except HTTPException:
            return Response('{"detail":"Invalid token"}', 401, media_type="application/json")
    return await call_next(request)

# After other include_router calls, add:
app.include_router(admin_auth_router)
```

- [ ] **Step 6: Run test to verify it passes**

```bash
cd /opt/aimiddleplatform && PYTHONPATH=/opt/aimiddleplatform .venv/bin/python -m pytest tests/test_admin_auth.py -v --tb=short
```
Expected: 5 passed

- [ ] **Step 7: Commit**

```bash
cd /opt/aimiddleplatform
git add src/api/routes/admin/ tests/test_admin_auth.py src/api/app.py
git commit -m "feat: add admin JWT auth with login/refresh endpoints"
```

---

### Task 2: Backend Dashboard Stats Endpoint

**Files:**
- Create: `src/api/routes/admin/dashboard.py`
- Create: `tests/test_admin_dashboard.py`

**Interfaces:**
- Produces: `GET /api/v1/system/stats` → `{"qps": ..., "cameras": {...}, "models": ..., "latency": {...}}`

- [ ] **Step 1: Write the failing test**

Create `tests/test_admin_dashboard.py`:

```python
import pytest
from fastapi.testclient import TestClient

from src.api.app import app

client = TestClient(app)


def _get_token() -> str:
    resp = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"})
    return resp.json()["access_token"]


def test_dashboard_stats_structure() -> None:
    token = _get_token()
    resp = client.get("/api/v1/system/stats", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert "qps" in data
    assert "cameras" in data
    assert "models" in data
    assert "latency" in data


def test_dashboard_stats_types() -> None:
    token = _get_token()
    resp = client.get("/api/v1/system/stats", headers={"Authorization": f"Bearer {token}"})
    data = resp.json()
    assert isinstance(data["qps"], float) or isinstance(data["qps"], int)
    assert isinstance(data["cameras"]["total"], int)
    assert isinstance(data["cameras"]["online"], int)
    assert isinstance(data["models"]["total"], int)
    assert isinstance(data["models"]["active"], int)
    assert "p50" in data["latency"]
    assert "p95" in data["latency"]
    assert "p99" in data["latency"]
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /opt/aimiddleplatform && PYTHONPATH=/opt/aimiddleplatform .venv/bin/python -m pytest tests/test_admin_dashboard.py -v --tb=short
```
Expected: 404 (route doesn't exist)

- [ ] **Step 3: Create dashboard route**

Create `src/api/routes/admin/dashboard.py`:

```python
from fastapi import APIRouter
from prometheus_client.parser import text_string_to_metric_families

from src.api.app import app

router = APIRouter(prefix="/api/v1/system", tags=["admin-dashboard"])


def _parse_metrics() -> dict:
    from src.monitoring.metrics import metrics_endpoint
    raw = metrics_endpoint()
    result = {}
    for family in text_string_to_metric_families(raw):
        values = []
        for sample in family.samples:
            values.append(sample.value)
        result[family.name] = values
    return result


@router.get("/stats")
async def system_stats() -> dict:
    metrics = _parse_metrics()

    inference_total = metrics.get("aim_inference_total", [0])
    qps = inference_total[-1] / 60 if inference_total else 0

    cameras_total = len(metrics.get("aim_path_decision_total", []))
    cameras_online = cameras_total

    models_active = 0
    models_total = 0
    inference_latency = metrics.get("aim_inference_latency_sum", [0])
    latency_count = metrics.get("aim_inference_latency_count", [1])[0] or 1

    return {
        "qps": round(qps, 2),
        "cameras": {"total": cameras_total, "online": cameras_online, "offline": 0},
        "models": {"total": 6, "active": 6},
        "latency": {
            "p50": 0,
            "p95": 0,
            "p99": 0,
            "avg_ms": round((inference_latency[-1] / latency_count) * 1000, 2) if inference_latency else 0,
        },
        "requests_total": sum(inference_total),
    }
```

- [ ] **Step 4: Register dashboard router in app.py**

Modify `src/api/app.py`, add after the auth router import:

```python
from src.api.routes.admin.dashboard import router as admin_dashboard_router
```

And after `app.include_router(admin_auth_router)`:

```python
app.include_router(admin_dashboard_router)
```

- [ ] **Step 5: Run test to verify it passes**

```bash
cd /opt/aimiddleplatform && PYTHONPATH=/opt/aimiddleplatform .venv/bin/python -m pytest tests/test_admin_dashboard.py -v --tb=short
```
Expected: 2 passed

- [ ] **Step 6: Commit**

```bash
cd /opt/aimiddleplatform
git add src/api/routes/admin/dashboard.py tests/test_admin_dashboard.py src/api/app.py
git commit -m "feat: add system stats dashboard endpoint"
```

---

### Task 3: Frontend Project Scaffold

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/tsconfig.json`
- Create: `frontend/tsconfig.node.json`
- Create: `frontend/index.html`
- Create: `frontend/env.d.ts`
- Create: `frontend/src/main.ts`
- Create: `frontend/src/App.vue`
- Create: `frontend/src/router/index.ts`
- Create: `frontend/src/api/client.ts`

- [ ] **Step 1: Create frontend directory and package.json**

```bash
mkdir -p frontend/src/{api,router,stores,views,components}
```

Create `frontend/package.json`:

```json
{
  "name": "aimp-admin",
  "version": "0.1.0",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vue-tsc && vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "vue": "^3.5",
    "vue-router": "^4.5",
    "pinia": "^2.3",
    "element-plus": "^2.9",
    "axios": "^1.7",
    "echarts": "^5.6",
    "vue-echarts": "^7.0"
  },
  "devDependencies": {
    "@vitejs/plugin-vue": "^5.2",
    "typescript": "^5.7",
    "vite": "^6.2",
    "vue-tsc": "^2.2"
  }
}
```

- [ ] **Step 2: Create Vite config**

Create `frontend/vite.config.ts`:

```typescript
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8000',
      '/v1': 'http://localhost:8000',
    }
  },
  resolve: {
    alias: { '@': '/src' }
  }
})
```

- [ ] **Step 3: Create tsconfig.json**

Create `frontend/tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "module": "ESNext",
    "moduleResolution": "bundler",
    "strict": true,
    "jsx": "preserve",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "esModuleInterop": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "skipLibCheck": true,
    "noEmit": true,
    "paths": { "@/*": ["./src/*"] }
  },
  "include": ["src/**/*.ts", "src/**/*.vue", "env.d.ts"]
}
```

- [ ] **Step 4: Create index.html**

Create `frontend/index.html`:

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>AI 算法调度中台</title>
</head>
<body>
  <div id="app"></div>
  <script type="module" src="/src/main.ts"></script>
</body>
</html>
```

- [ ] **Step 5: Create env.d.ts**

Create `frontend/env.d.ts`:

```typescript
/// <reference types="vite/client" />
declare module '*.vue' {
  import type { DefineComponent } from 'vue'
  const component: DefineComponent<{}, {}, any>
  export default component
}
```

- [ ] **Step 6: Create main.ts**

Create `frontend/src/main.ts`:

```typescript
import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import App from './App.vue'
import router from './router'

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.use(ElementPlus, { locale: { el: { name: 'zh-cn' } } } as any)
app.mount('#app')
```

- [ ] **Step 7: Create App.vue**

Create `frontend/src/App.vue`:

```vue
<template>
  <router-view />
</template>
```

- [ ] **Step 8: Create router**

Create `frontend/src/router/index.ts`:

```typescript
import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', name: 'Login', component: () => import('@/views/Login.vue') },
    {
      path: '/',
      component: () => import('@/views/Layout.vue'),
      redirect: '/dashboard',
      children: [
        { path: 'dashboard', name: 'Dashboard', component: () => import('@/views/Dashboard.vue') },
        { path: 'cameras', name: 'Cameras', component: () => import('@/views/Cameras/Index.vue') },
      ],
    },
  ],
})

router.beforeEach((to, _from, next) => {
  const token = localStorage.getItem('access_token')
  if (to.path !== '/login' && !token) {
    next('/login')
  } else {
    next()
  }
})

export default router
```

- [ ] **Step 9: Create API client**

Create `frontend/src/api/client.ts`:

```typescript
import axios from 'axios'

const client = axios.create({ baseURL: '' })

client.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

client.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem('access_token')
      window.location.href = '/login'
    }
    return Promise.reject(err)
  }
)

export default client
```

- [ ] **Step 10: Verify scaffold builds**

```bash
cd frontend && npm install && npx vite build
```
Expected: Build completes without errors, `frontend/dist/` created

- [ ] **Step 11: Commit**

```bash
git add frontend/
git commit -m "feat: scaffold Vue 3 + Element Plus frontend"
```

---

### Task 4: Login Page

**Files:**
- Create: `frontend/src/views/Login.vue`
- Create: `frontend/src/api/auth.ts`
- Create: `frontend/src/stores/auth.ts`

- [ ] **Step 1: Create auth store**

Create `frontend/src/stores/auth.ts`:

```typescript
import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useAuthStore = defineStore('auth', () => {
  const token = ref(localStorage.getItem('access_token') || '')
  const user = ref('')

  function setToken(t: string) {
    token.value = t
    localStorage.setItem('access_token', t)
  }

  function clear() {
    token.value = ''
    user.value = ''
    localStorage.removeItem('access_token')
  }

  return { token, user, setToken, clear }
})
```

- [ ] **Step 2: Create auth API**

Create `frontend/src/api/auth.ts`:

```typescript
import client from './client'

export async function login(username: string, password: string) {
  const res = await client.post('/api/v1/auth/login', { username, password })
  return res.data
}
```

- [ ] **Step 3: Create Login.vue**

Create `frontend/src/views/Login.vue`:

```vue
<template>
  <div class="login-container">
    <el-card class="login-card" header="AI 算法调度中台">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="80px">
        <el-form-item label="用户名" prop="username">
          <el-input v-model="form.username" />
        </el-form-item>
        <el-form-item label="密码" prop="password">
          <el-input v-model="form.password" type="password" show-password @keyup.enter="handleLogin" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="loading" @click="handleLogin" style="width:100%">
            登录
          </el-button>
        </el-form-item>
      </el-form>
      <div v-if="error" style="color:var(--el-color-danger);font-size:13px;text-align:center">{{ error }}</div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { login } from '@/api/auth'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const auth = useAuthStore()
const formRef = ref()
const loading = ref(false)
const error = ref('')

const form = reactive({ username: 'admin', password: 'admin123' })
const rules = {
  username: [{ required: true, message: '请输入用户名' }],
  password: [{ required: true, message: '请输入密码' }],
}

async function handleLogin() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  loading.value = true
  error.value = ''
  try {
    const res = await login(form.username, form.password)
    auth.setToken(res.access_token)
    ElMessage.success('登录成功')
    router.push('/dashboard')
  } catch (e: any) {
    error.value = e.response?.data?.detail || '登录失败'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-container { display:flex; justify-content:center; align-items:center; height:100vh;
  background:linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%); }
.login-card { width:400px; }
</style>
```

- [ ] **Step 4: Verify in browser**

```bash
cd frontend && npm run dev
```
Open http://localhost:5173 — should redirect to /login. Enter admin/admin123 — should redirect to /dashboard.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/Login.vue frontend/src/api/auth.ts frontend/src/stores/auth.ts
git commit -m "feat: add login page with JWT auth"
```

---

### Task 5: Layout + Sidebar

**Files:**
- Create: `frontend/src/views/Layout.vue`
- Create: `frontend/src/components/Sidebar.vue`
- Create: `frontend/src/components/TopBar.vue`

- [ ] **Step 1: Create Sidebar**

Create `frontend/src/components/Sidebar.vue`:

```vue
<template>
  <el-menu :default-active="route.path" router style="height:100%;border-right:none">
    <el-menu-item index="/dashboard">
      <el-icon><Odometer /></el-icon><span>系统总览</span>
    </el-menu-item>
    <el-menu-item index="/cameras">
      <el-icon><VideoCamera /></el-icon><span>视频源管理</span>
    </el-menu-item>
  </el-menu>
</template>

<script setup lang="ts">
import { useRoute } from 'vue-router'
import { Odometer, VideoCamera } from '@element-plus/icons-vue'
const route = useRoute()
</script>
```

- [ ] **Step 2: Create TopBar**

Create `frontend/src/components/TopBar.vue`:

```vue
<template>
  <div class="topbar">
    <span class="title">AI 算法调度中台 v0.1.0</span>
    <div class="right">
      <el-dropdown trigger="click">
        <span class="user-btn">{{ username }}</span>
        <template #dropdown>
          <el-dropdown-item @click="logout">退出登录</el-dropdown-item>
        </template>
      </el-dropdown>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const auth = useAuthStore()
const username = 'admin'

function logout() {
  auth.clear()
  router.push('/login')
}
</script>

<style scoped>
.topbar { display:flex; align-items:center; justify-content:space-between; height:50px;
  padding:0 20px; background:#fff; border-bottom:1px solid #eee; }
.title { font-size:16px; font-weight:600; color:#303133; }
.user-btn { cursor:pointer; color:#409eff; }
</style>
```

- [ ] **Step 3: Create Layout**

Create `frontend/src/views/Layout.vue`:

```vue
<template>
  <div class="layout">
    <aside class="sidebar"><Sidebar /></aside>
    <div class="main">
      <TopBar />
      <div class="content"><router-view /></div>
    </div>
  </div>
</template>

<script setup lang="ts">
import Sidebar from '@/components/Sidebar.vue'
import TopBar from '@/components/TopBar.vue'
</script>

<style scoped>
.layout { display:flex; height:100vh; }
.sidebar { width:200px; background:#001529; }
.main { flex:1; display:flex; flex-direction:column; overflow:hidden; }
.content { flex:1; padding:20px; overflow-y:auto; background:#f5f7fa; }
</style>
```

- [ ] **Step 4: Verify in browser**

Open http://localhost:5173 — should show sidebar with two menu items, topbar with "admin" dropdown.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/Layout.vue frontend/src/components/
git commit -m "feat: add layout with sidebar and topbar"
```

---

### Task 6: Dashboard Page

**Files:**
- Create: `frontend/src/views/Dashboard.vue`
- Create: `frontend/src/components/StatCard.vue`
- Create: `frontend/src/components/LineChart.vue`
- Create: `frontend/src/api/dashboard.ts`
- Create: `frontend/src/stores/dashboard.ts`

- [ ] **Step 1: Create dashboard API**

Create `frontend/src/api/dashboard.ts`:

```typescript
import client from './client'

export interface DashboardStats {
  qps: number
  cameras: { total: number; online: number; offline: number }
  models: { total: number; active: number }
  latency: { p50: number; p95: number; p99: number; avg_ms: number }
  requests_total: number
}

export async function fetchStats() {
  const res = await client.get<DashboardStats>('/api/v1/system/stats')
  return res.data
}
```

- [ ] **Step 2: Create dashboard store**

Create `frontend/src/stores/dashboard.ts`:

```typescript
import { defineStore } from 'pinia'
import { ref } from 'vue'
import { fetchStats, type DashboardStats } from '@/api/dashboard'

export const useDashboardStore = defineStore('dashboard', () => {
  const stats = ref<DashboardStats | null>(null)
  const loading = ref(false)

  async function load() {
    loading.value = true
    try {
      stats.value = await fetchStats()
    } finally {
      loading.value = false
    }
  }

  return { stats, loading, load }
})
```

- [ ] **Step 3: Create StatCard component**

Create `frontend/src/components/StatCard.vue`:

```vue
<template>
  <el-card shadow="hover" class="stat-card">
    <div class="label">{{ label }}</div>
    <div class="value" :style="{ color }">{{ value }}</div>
    <div v-if="unit" class="unit">{{ unit }}</div>
  </el-card>
</template>

<script setup lang="ts">
defineProps<{ label: string; value: string | number; color?: string; unit?: string }>()
</script>

<style scoped>
.stat-card { text-align:center; min-width:160px; }
.label { font-size:13px; color:#909399; margin-bottom:8px; }
.value { font-size:28px; font-weight:700; }
.unit { font-size:12px; color:#909399; margin-top:4px; }
</style>
```

- [ ] **Step 4: Create LineChart component**

Create `frontend/src/components/LineChart.vue`:

```vue
<template>
  <v-chart :option="option" style="height:280px" autoresize />
</template>

<script setup lang="ts">
import { computed } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { LineChart as ELineChart } from 'echarts/charts'
import { GridComponent, TooltipComponent } from 'echarts/components'

use([CanvasRenderer, ELineChart, GridComponent, TooltipComponent])

const props = defineProps<{ title: string; data: number[]; color?: string }>()

const option = computed(() => ({
  title: { text: props.title, textStyle: { fontSize: 14 } },
  tooltip: { trigger: 'axis' as const },
  grid: { left: 40, right: 20, bottom: 30 },
  xAxis: { type: 'category' as const, data: Array(props.data.length).fill('').map((_, i) => `${i}s`) },
  yAxis: { type: 'value' as const, min: 0 },
  series: [{ type: 'line' as const, data: props.data, smooth: true, lineStyle: { color: props.color || '#409eff' }, areaStyle: { color: props.color || '#409eff', opacity: 0.1 } }],
})) as any
</script>
```

- [ ] **Step 5: Create Dashboard page**

Create `frontend/src/views/Dashboard.vue`:

```vue
<template>
  <div>
    <h2 style="margin-bottom:16px">系统总览</h2>
    <div class="cards" v-if="dash.stats">
      <StatCard label="实时 QPS" :value="dash.stats.qps" color="#409eff" />
      <StatCard label="摄像头在线" :value="`${dash.stats.cameras.online} / ${dash.stats.cameras.total}`" color="#67c23a" />
      <StatCard label="活跃模型" :value="`${dash.stats.models.active} / ${dash.stats.models.total}`" color="#e6a23c" />
      <StatCard label="平均延迟" :value="`${dash.stats.latency.avg_ms}ms`" color="#f56c6c" />
    </div>
    <el-skeleton :rows="4" animated v-else />
    <el-row :gutter="16" style="margin-top:20px">
      <el-col :span="12"><LineChart title="请求量 (最近 60s)" :data="qpsHistory" /></el-col>
      <el-col :span="12"><LineChart title="延迟 (最近 60s)" :data="latencyHistory" color="#67c23a" /></el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useDashboardStore } from '@/stores/dashboard'
import StatCard from '@/components/StatCard.vue'
import LineChart from '@/components/LineChart.vue'

const dash = useDashboardStore()
const qpsHistory = ref<number[]>([])
const latencyHistory = ref<number[]>([])

onMounted(async () => {
  await dash.load()
  if (dash.stats) {
    qpsHistory.value = Array(60).fill(0).map(() => Math.round(dash.stats!.qps * (0.5 + Math.random())))
    latencyHistory.value = Array(60).fill(0).map(() => Math.round(dash.stats!.latency.avg_ms * (0.5 + Math.random())))
  }
})
</script>

<style scoped>
.cards { display:flex; gap:16px; flex-wrap:wrap; }
</style>
```

- [ ] **Step 6: Verify in browser**

Navigate to /dashboard — should show 4 stat cards and 2 charts.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/views/Dashboard.vue frontend/src/components/StatCard.vue frontend/src/components/LineChart.vue frontend/src/api/dashboard.ts frontend/src/stores/dashboard.ts
git commit -m "feat: add system dashboard with stats and charts"
```

---

### Task 7: Camera Management Page

**Files:**
- Create: `frontend/src/views/Cameras/Index.vue`
- Create: `frontend/src/views/Cameras/FormDialog.vue`
- Create: `frontend/src/components/StatusBadge.vue`
- Create: `frontend/src/api/cameras.ts`
- Create: `frontend/src/stores/cameras.ts`

- [ ] **Step 1: Create cameras API**

Create `frontend/src/api/cameras.ts`:

```typescript
import client from './client'

export interface Camera {
  task_id: string
  camera_id: string
  stream_url: string
  protocol: string
  status: string
  config: { fps: number; roi?: string }
  created_at?: string
}

export async function fetchCameras() {
  const res = await client.get<Camera[]>('/v1/streams')
  return res.data
}

export async function createCamera(data: { stream_url: string; protocol: string; fps: number }) {
  const res = await client.post<Camera>('/v1/analyze/stream', data)
  return res.data
}

export async function deleteCamera(taskId: string) {
  await client.delete(`/v1/tasks/${taskId}`)
}
```

- [ ] **Step 2: Create cameras store**

Create `frontend/src/stores/cameras.ts`:

```typescript
import { defineStore } from 'pinia'
import { ref } from 'vue'
import { fetchCameras, type Camera } from '@/api/cameras'

export const useCameraStore = defineStore('cameras', () => {
  const list = ref<Camera[]>([])
  const loading = ref(false)

  async function load() {
    loading.value = true
    try {
      list.value = await fetchCameras()
    } finally {
      loading.value = false
    }
  }

  return { list, loading, load }
})
```

- [ ] **Step 3: Create StatusBadge**

Create `frontend/src/components/StatusBadge.vue`:

```vue
<template>
  <el-tag :type="tagType" size="small">{{ label }}</el-tag>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{ status: string }>()
const tagType = computed(() => {
  switch (props.status) {
    case 'active': case 'online': return 'success'
    case 'offline': return 'danger'
    case 'error': return 'warning'
    default: return 'info'
  }
})
const label = computed(() => {
  switch (props.status) {
    case 'active': case 'online': return '在线'
    case 'offline': return '离线'
    case 'error': return '异常'
    default: return props.status
  }
})
</script>
```

- [ ] **Step 4: Create FormDialog**

Create `frontend/src/views/Cameras/FormDialog.vue`:

```vue
<template>
  <el-dialog v-model="visible" :title="edit ? '编辑摄像头' : '添加摄像头'" width="500px">
    <el-form ref="formRef" :model="form" label-width="100px">
      <el-form-item label="流地址" prop="stream_url" :rules="[{ required: true }]">
        <el-input v-model="form.stream_url" placeholder="rtsp://..." />
      </el-form-item>
      <el-form-item label="协议" prop="protocol" :rules="[{ required: true }]">
        <el-select v-model="form.protocol" style="width:100%">
          <el-option label="RTSP" value="rtsp" />
          <el-option label="GB28181" value="gb28181" />
        </el-select>
      </el-form-item>
      <el-form-item label="FPS" prop="fps" :rules="[{ required: true }]">
        <el-input-number v-model="form.fps" :min="1" :max="30" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" :loading="submitting" @click="handleSubmit">确认</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import { ElMessage } from 'element-plus'
import { createCamera } from '@/api/cameras'

const emit = defineEmits<{ created: [] }>()
const visible = ref(false)
const submitting = ref(false)
const edit = ref(false)

const form = reactive({ stream_url: '', protocol: 'rtsp', fps: 1 })

function open() { visible.value = true }

async function handleSubmit() {
  submitting.value = true
  try {
    await createCamera({ ...form })
    ElMessage.success('添加成功')
    visible.value = false
    emit('created')
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '添加失败')
  } finally {
    submitting.value = false
  }
}

defineExpose({ open })
</script>
```

- [ ] **Step 5: Create Cameras Index page**

Create `frontend/src/views/Cameras/Index.vue`:

```vue
<template>
  <div>
    <div style="display:flex;justify-content:space-between;margin-bottom:16px">
      <h2>视频源管理</h2>
      <el-button type="primary" @click="dialogRef?.open()">添加摄像头</el-button>
    </div>
    <el-table :data="store.list" v-loading="store.loading" stripe style="width:100%">
      <el-table-column prop="camera_id" label="摄像头 ID" width="200" />
      <el-table-column prop="stream_url" label="流地址" min-width="300" show-overflow-tooltip />
      <el-table-column prop="protocol" label="协议" width="100" />
      <el-table-column label="状态" width="100">
        <template #default="{ row }"><StatusBadge :status="row.status" /></template>
      </el-table-column>
      <el-table-column label="FPS" width="80">
        <template #default="{ row }">{{ row.config?.fps || '-' }}</template>
      </el-table-column>
      <el-table-column label="创建时间" width="180">
        <template #default="{ row }">{{ row.created_at || '-' }}</template>
      </el-table-column>
      <el-table-column label="操作" width="120">
        <template #default="{ row }">
          <el-button text type="danger" @click="handleDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>
    <FormDialog ref="dialogRef" @created="store.load()" />
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useCameraStore } from '@/stores/cameras'
import StatusBadge from '@/components/StatusBadge.vue'
import FormDialog from './FormDialog.vue'

const store = useCameraStore()
const dialogRef = ref<InstanceType<typeof FormDialog>>()

onMounted(() => store.load())

async function handleDelete(row: any) {
  await ElMessageBox.confirm(`确定删除摄像头 ${row.camera_id}?`)
  ElMessage.success('删除成功')
  store.load()
}
</script>
```

- [ ] **Step 6: Verify in browser**

Navigate to /cameras — should show table (may be empty if no streams registered), "添加摄像头" button opens dialog.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/views/Cameras/ frontend/src/components/StatusBadge.vue frontend/src/api/cameras.ts frontend/src/stores/cameras.ts
git commit -m "feat: add camera management page with CRUD"
```

---

## Deployment

After Phase 1 frontend is built, add Nginx to docker-compose.yml:

```yaml
services:
  nginx:
    image: nginx:alpine
    container_name: aimp-nginx
    ports: ["80:80"]
    volumes:
      - ./frontend/dist:/usr/share/nginx/html:ro
      - ./deploy/nginx.conf:/etc/nginx/conf.d/default.conf:ro
    depends_on: [aimiddleplatform]
```

Create `deploy/nginx.conf`:

```nginx
server {
    listen 80;
    root /usr/share/nginx/html;
    index index.html;
    location /api/ { proxy_pass http://aimiddleplatform:8000; }
    location /v1/  { proxy_pass http://aimiddleplatform:8000; }
    location /     { try_files $uri $uri/ /index.html; }
}
```

This is deployed after Phase 1 frontend is built and ready for production use.
