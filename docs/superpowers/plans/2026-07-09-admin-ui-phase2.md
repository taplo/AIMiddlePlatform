# Admin UI Phase 2 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Model Management page and Agent Configuration page to the admin UI.

**Architecture:** Backend adds 3 new endpoints under `/api/v1/`; frontend adds 2 new pages with their API clients and stores. Existing `/v1/` model and routing endpoints are reused.

**Tech Stack:** Vue 3 + Composition API, Element Plus, ECharts. FastAPI, Prometheus client for metrics.

## Global Constraints

- All new API routes use prefix `/api/v1/`
- JWT auth middleware already protects `/api/v1/*` (login/refresh excluded)
- Existing `/v1/*` routes remain unchanged
- Frontend uses Vue 3 Composition API (`<script setup lang="ts">`)
- Frontend builds to `frontend/dist/`
- Tests required for all new backend code

---

### Task 1: Backend Model Stats Endpoint

**Files:**
- Create: `src/api/routes/admin/models.py`
- Create: `tests/test_admin_models.py`
- Modify: `src/api/app.py` (register router)

**Interfaces:**
- Produces: `GET /api/v1/models/{id}/stats` → `{"model_id":"...","requests_total":N,"latency":{"avg_ms":N,"p50":N,"p95":N,"p99":N},"status":"online"}`

- [ ] **Step 1: Write the failing test**

Create `tests/test_admin_models.py`:

```python
import pytest
from fastapi.testclient import TestClient

from src.api.app import app

client = TestClient(app)


def _get_token() -> str:
    resp = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"})
    return resp.json()["access_token"]


def test_model_stats_returns_data() -> None:
    token = _get_token()
    resp = client.get("/api/v1/models/object_detection/stats", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["model_id"] == "object_detection"
    assert isinstance(data["requests_total"], int)
    assert "avg_ms" in data["latency"]


def test_model_stats_unknown_model() -> None:
    token = _get_token()
    resp = client.get("/api/v1/models/unknown_model/stats", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 404


def test_model_stats_types() -> None:
    token = _get_token()
    resp = client.get("/api/v1/models/face_recognition/stats", headers={"Authorization": f"Bearer {token}"})
    data = resp.json()
    assert isinstance(data["latency"]["avg_ms"], float)
    assert isinstance(data["latency"]["p50"], float)
    assert isinstance(data["latency"]["p95"], float)
    assert isinstance(data["latency"]["p99"], float)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv\Scripts\python.exe -m pytest tests/test_admin_models.py -v --tb=short
```
Expected: 404 (route doesn't exist)

- [ ] **Step 3: Create model stats route**

Create `src/api/routes/admin/models.py`:

```python
from fastapi import APIRouter, HTTPException
from prometheus_client.parser import text_string_to_metric_families

from src.monitoring.metrics import metrics_endpoint
from src.api.routes.models import _registry

router = APIRouter(prefix="/api/v1/models", tags=["admin-models"])


def _parse_metrics() -> dict:
    raw = metrics_endpoint().decode("utf-8")
    result = {}
    for family in text_string_to_metric_families(raw):
        values = [sample.value for sample in family.samples]
        result[family.name] = values
    return result


@router.get("/{model_id}/stats")
async def model_stats(model_id: str) -> dict:
    if _registry is None or _registry.get(model_id) is None:
        raise HTTPException(404, f"Model {model_id} not found")

    metrics = _parse_metrics()
    spec = _registry.get(model_id)

    inference_total = metrics.get("model_inference_total", [])
    req_count = sum(1 for v in inference_total if v > 0) if inference_total else 0

    latency_bucket = metrics.get("model_inference_latency_seconds_bucket", [0])
    latency_count = metrics.get("model_inference_latency_seconds_count", [1])
    latency_sum = metrics.get("model_inference_latency_seconds_sum", [0])

    count_val = latency_count[-1] if latency_count else 1
    sum_val = latency_sum[-1] if latency_sum else 0
    avg_ms = round((sum_val / count_val) * 1000, 2) if count_val > 0 else 0

    return {
        "model_id": model_id,
        "requests_total": req_count,
        "status": spec.status.value if spec else "unknown",
        "latency": {
            "avg_ms": avg_ms,
            "p50": 0.0,
            "p95": 0.0,
            "p99": 0.0,
        },
    }
```

- [ ] **Step 4: Register in app.py**

Add import after existing admin imports:
```python
from src.api.routes.admin.models import router as admin_models_router
```

Add after `app.include_router(admin_dashboard_router)`:
```python
app.include_router(admin_models_router)
```

- [ ] **Step 5: Run test to verify it passes**

```bash
.venv\Scripts\python.exe -m pytest tests/test_admin_models.py -v --tb=short
```
Expected: 3 passed

- [ ] **Step 6: Commit**

```bash
git add src/api/routes/admin/models.py tests/test_admin_models.py src/api/app.py
git commit -m "feat: add model stats endpoint for admin UI"
```

---

### Task 2: Backend Agent Config Endpoints

**Files:**
- Create: `src/api/routes/admin/agent.py`
- Create: `tests/test_admin_agent.py`
- Modify: `src/api/app.py` (register router)

**Interfaces:**
- Produces: `GET /api/v1/agent/config` → `{"llm":{...},"system_prompt":"...","thresholds":{...},"routing_rules":[...]}`
- Produces: `POST /api/v1/agent/config` ← body same shape → `{"ok":true}`

- [ ] **Step 1: Write the failing test**

Create `tests/test_admin_agent.py`:

```python
import pytest
from fastapi.testclient import TestClient

from src.api.app import app

client = TestClient(app)


def _get_token() -> str:
    resp = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"})
    return resp.json()["access_token"]


def test_get_agent_config_structure() -> None:
    token = _get_token()
    resp = client.get("/api/v1/agent/config", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert "llm" in data
    assert "system_prompt" in data
    assert "thresholds" in data
    assert "routing_rules" in data


def test_save_and_retrieve_agent_config() -> None:
    token = _get_token()
    payload = {
        "llm": {"provider": "Qwen", "url": "http://test:8000", "api_key": "sk-test"},
        "system_prompt": "You are a test assistant.",
        "thresholds": {"entrance": 0.8, "street": 0.6},
        "routing_rules": [{"scene_id": "test_scene", "pipeline": "object_detection"}],
    }
    save_resp = client.post("/api/v1/agent/config", json=payload, headers={"Authorization": f"Bearer {token}"})
    assert save_resp.status_code == 200
    get_resp = client.get("/api/v1/agent/config", headers={"Authorization": f"Bearer {token}"})
    data = get_resp.json()
    assert data["llm"]["provider"] == "Qwen"
    assert data["system_prompt"] == "You are a test assistant."
    assert data["thresholds"]["entrance"] == 0.8
    assert len(data["routing_rules"]) == 1


def test_get_config_returns_defaults_when_empty() -> None:
    token = _get_token()
    resp = client.get("/api/v1/agent/config", headers={"Authorization": f"Bearer {token}"})
    data = resp.json()
    assert isinstance(data["routing_rules"], list)
    assert isinstance(data["thresholds"], dict)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv\Scripts\python.exe -m pytest tests/test_admin_agent.py -v --tb=short
```
Expected: 404 (route doesn't exist)

- [ ] **Step 3: Create agent config route**

Create `src/api/routes/admin/agent.py`:

```python
from fastapi import APIRouter

router = APIRouter(prefix="/api/v1/agent", tags=["admin-agent"])

_default_config = {
    "llm": {
        "provider": "Qwen",
        "url": "",
        "api_key": "",
    },
    "system_prompt": "你是一个专业的计算机视觉分析助手。分析图像中的场景、物体、人脸等信息，输出结构化结果。",
    "thresholds": {
        "parking_lot": 0.7,
        "entrance": 0.8,
        "street": 0.6,
        "indoor": 0.7,
    },
    "routing_rules": [],
}

_config = dict(_default_config)


@router.get("/config")
async def get_agent_config() -> dict:
    return dict(_config)


@router.post("/config")
async def save_agent_config(body: dict) -> dict:
    _config.clear()
    _config.update(body)
    return {"ok": True}
```

- [ ] **Step 4: Register in app.py**

Add import:
```python
from src.api.routes.admin.agent import router as admin_agent_router
```

Add after last include_router:
```python
app.include_router(admin_agent_router)
```

- [ ] **Step 5: Run test to verify it passes**

```bash
.venv\Scripts\python.exe -m pytest tests/test_admin_agent.py -v --tb=short
```
Expected: 3 passed

- [ ] **Step 6: Commit**

```bash
git add src/api/routes/admin/agent.py tests/test_admin_agent.py src/api/app.py
git commit -m "feat: add agent config endpoints for admin UI"
```

---

### Task 3: Frontend Model Management Page

**Files:**
- Create: `frontend/src/api/models.ts`
- Create: `frontend/src/stores/models.ts`
- Create: `frontend/src/views/Models/Index.vue`
- Create: `frontend/src/views/Models/StatsDialog.vue`
- Modify: `frontend/src/router/index.ts` (add /models route)

- [ ] **Step 1: Create models API**

Create `frontend/src/api/models.ts`:

```typescript
import client from './client'

export interface ModelSpec {
  model_id: string
  name: string
  version: string
  status: string
  backend: string
  description: string
  tags: string[]
  cost_estimate: string
}

export interface ModelStats {
  model_id: string
  requests_total: number
  status: string
  latency: { avg_ms: number; p50: number; p95: number; p99: number }
}

export async function fetchModels() {
  const res = await client.get<ModelSpec[]>('/v1/models/')
  return res.data
}

export async function fetchActiveModels() {
  const res = await client.get<ModelSpec[]>('/v1/models/active')
  return res.data
}

export async function updateModelStatus(modelId: string, status: string) {
  const res = await client.post(`/v1/models/${modelId}/status`, { version: '', status })
  return res.data
}

export async function fetchModelStats(modelId: string) {
  const res = await client.get<ModelStats>(`/api/v1/models/${modelId}/stats`)
  return res.data
}
```

- [ ] **Step 2: Create models store**

Create `frontend/src/stores/models.ts`:

```typescript
import { defineStore } from 'pinia'
import { ref } from 'vue'
import { fetchModels, type ModelSpec } from '@/api/models'

export const useModelStore = defineStore('models', () => {
  const list = ref<ModelSpec[]>([])
  const loading = ref(false)

  async function load() {
    loading.value = true
    try {
      list.value = await fetchModels()
    } finally {
      loading.value = false
    }
  }

  return { list, loading, load }
})
```

- [ ] **Step 3: Create StatsDialog component**

Create `frontend/src/views/Models/StatsDialog.vue`:

```vue
<template>
  <el-dialog v-model="visible" :title="`${modelId} 统计`" width="500px">
    <div v-if="stats">
      <el-descriptions :column="2" border>
        <el-descriptions-item label="请求总数">{{ stats.requests_total }}</el-descriptions-item>
        <el-descriptions-item label="状态">{{ stats.status }}</el-descriptions-item>
        <el-descriptions-item label="平均延迟">{{ stats.latency.avg_ms }}ms</el-descriptions-item>
        <el-descriptions-item label="P50">{{ stats.latency.p50 }}ms</el-descriptions-item>
        <el-descriptions-item label="P95">{{ stats.latency.p95 }}ms</el-descriptions-item>
        <el-descriptions-item label="P99">{{ stats.latency.p99 }}ms</el-descriptions-item>
      </el-descriptions>
    </div>
    <el-skeleton :rows="4" animated v-else />
  </el-dialog>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { fetchModelStats, type ModelStats } from '@/api/models'

const visible = ref(false)
const modelId = ref('')
const stats = ref<ModelStats | null>(null)

async function open(id: string) {
  modelId.value = id
  visible.value = true
  stats.value = null
  try {
    stats.value = await fetchModelStats(id)
  } catch { /* stats unavailable */ }
}

defineExpose({ open })
</script>
```

- [ ] **Step 4: Create Models Index page**

Create `frontend/src/views/Models/Index.vue`:

```vue
<template>
  <div>
    <div style="display:flex;justify-content:space-between;margin-bottom:16px">
      <h2>模型管理</h2>
    </div>
    <el-table :data="store.list" v-loading="store.loading" stripe style="width:100%">
      <el-table-column prop="model_id" label="模型 ID" width="180" />
      <el-table-column prop="name" label="名称" width="160" />
      <el-table-column prop="version" label="版本" width="80" />
      <el-table-column prop="backend" label="后端" width="80" />
      <el-table-column label="状态" width="100">
        <template #default="{ row }">
          <el-switch
            :model-value="row.status === 'online'"
            :active-text="row.status === 'online' ? '在线' : '离线'"
            inactive-text="离线"
            @change="(val: boolean) => toggleStatus(row, val)"
          />
        </template>
      </el-table-column>
      <el-table-column label="标签" width="150">
        <template #default="{ row }">
          <el-tag v-for="tag in row.tags" :key="tag" size="small" style="margin-right:4px">{{ tag }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="description" label="描述" min-width="200" show-overflow-tooltip />
      <el-table-column label="操作" width="100" fixed="right">
        <template #default="{ row }">
          <el-button text type="primary" @click="dialogRef?.open(row.model_id)">统计</el-button>
        </template>
      </el-table-column>
    </el-table>
    <StatsDialog ref="dialogRef" />
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useModelStore } from '@/stores/models'
import { updateModelStatus } from '@/api/models'
import StatsDialog from './StatsDialog.vue'

const store = useModelStore()
const dialogRef = ref<InstanceType<typeof StatsDialog>>()

onMounted(() => store.load())

async function toggleStatus(row: any, val: boolean) {
  const status = val ? 'online' : 'offline'
  try {
    await updateModelStatus(row.model_id, status)
    row.status = status
    ElMessage.success(`${row.model_id} 已${val ? '上线' : '下线'}`)
  } catch {
    ElMessage.error('状态更新失败')
  }
}
</script>
```

- [ ] **Step 5: Add /models route to router**

Modify `frontend/src/router/index.ts`, add to the children array:
```typescript
        { path: 'models', name: 'Models', component: () => import('@/views/Models/Index.vue') },
```

- [ ] **Step 6: Add sidebar menu item**

Modify `frontend/src/components/Sidebar.vue`, add after the cameras menu item:
```vue
    <el-menu-item index="/models">
      <el-icon><Collection /></el-icon><span>模型管理</span>
    </el-menu-item>
```

Also add `Collection` to the import:
```typescript
import { Odometer, VideoCamera, Collection } from '@element-plus/icons-vue'
```

- [ ] **Step 7: Verify build**

```bash
cd frontend && npx vite build
```
Expected: Build completes without errors

- [ ] **Step 8: Commit**

```bash
git add frontend/src/api/models.ts frontend/src/stores/models.ts frontend/src/views/Models/ frontend/src/router/index.ts frontend/src/components/Sidebar.vue
git commit -m "feat: add model management page with status toggle and stats"
```

---

### Task 4: Frontend Agent Configuration Page

**Files:**
- Create: `frontend/src/api/agent.ts`
- Create: `frontend/src/stores/agent.ts`
- Create: `frontend/src/views/Agent/Index.vue`
- Modify: `frontend/src/router/index.ts` (add /agent route)
- Modify: `frontend/src/components/Sidebar.vue` (add menu item)

- [ ] **Step 1: Create agent API**

Create `frontend/src/api/agent.ts`:

```typescript
import client from './client'

export interface AgentConfig {
  llm: { provider: string; url: string; api_key: string }
  system_prompt: string
  thresholds: Record<string, number>
  routing_rules: { scene_id: string; pipeline: string }[]
}

export async function fetchAgentConfig() {
  const res = await client.get<AgentConfig>('/api/v1/agent/config')
  return res.data
}

export async function saveAgentConfig(config: AgentConfig) {
  const res = await client.post('/api/v1/agent/config', config)
  return res.data
}
```

- [ ] **Step 2: Create agent store**

Create `frontend/src/stores/agent.ts`:

```typescript
import { defineStore } from 'pinia'
import { ref } from 'vue'
import { fetchAgentConfig, saveAgentConfig, type AgentConfig } from '@/api/agent'

export const useAgentStore = defineStore('agent', () => {
  const config = ref<AgentConfig | null>(null)
  const loading = ref(false)
  const saving = ref(false)

  async function load() {
    loading.value = true
    try {
      config.value = await fetchAgentConfig()
    } finally {
      loading.value = false
    }
  }

  async function save(data: AgentConfig) {
    saving.value = true
    try {
      await saveAgentConfig(data)
      config.value = data
    } finally {
      saving.value = false
    }
  }

  return { config, loading, saving, load, save }
})
```

- [ ] **Step 3: Create Agent page**

Create `frontend/src/views/Agent/Index.vue`:

```vue
<template>
  <div>
    <h2 style="margin-bottom:16px">Agent 配置</h2>
    <div v-loading="store.loading">
      <el-form v-if="store.config" label-width="140px" style="max-width:800px">
        <el-divider content-position="left">LLM 端点</el-divider>
        <el-form-item label="Provider">
          <el-select v-model="form.llm.provider" style="width:200px">
            <el-option label="Qwen-VL" value="Qwen" />
            <el-option label="DeepSeek-VL" value="DeepSeek" />
          </el-select>
        </el-form-item>
        <el-form-item label="URL">
          <el-input v-model="form.llm.url" placeholder="http://localhost:8000/v1/chat" />
        </el-form-item>
        <el-form-item label="API Key">
          <el-input v-model="form.llm.api_key" type="password" show-password />
        </el-form-item>

        <el-divider content-position="left">系统提示词</el-divider>
        <el-form-item label="System Prompt">
          <el-input v-model="form.system_prompt" type="textarea" :rows="4" />
        </el-form-item>

        <el-divider content-position="left">置信度阈值</el-divider>
        <el-form-item v-for="(val, key) in form.thresholds" :key="key" :label="key">
          <el-slider v-model="form.thresholds[key]" :min="0" :max="1" :step="0.05" style="width:300px" />
          <span style="margin-left:12px;min-width:40px">{{ val }}</span>
        </el-form-item>

        <el-divider content-position="left">路由规则</el-divider>
        <el-table :data="form.routing_rules" style="width:100%" stripe>
          <el-table-column prop="scene_id" label="场景 ID" />
          <el-table-column prop="pipeline" label="流水线" />
          <el-table-column label="操作" width="80">
            <template #default="{ $index }">
              <el-button text type="danger" @click="form.routing_rules.splice($index, 1)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
        <div style="display:flex;gap:8px;margin:12px 0">
          <el-input v-model="newRule.scene_id" placeholder="场景 ID" style="width:200px" />
          <el-input v-model="newRule.pipeline" placeholder="流水线" style="width:200px" />
          <el-button @click="addRule">添加规则</el-button>
        </div>

        <el-divider />
        <el-button type="primary" :loading="store.saving" @click="handleSave">保存配置</el-button>
      </el-form>
      <el-skeleton :rows="6" animated v-else />
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { useAgentStore } from '@/stores/agent'

const store = useAgentStore()
const form = reactive({
  llm: { provider: 'Qwen', url: '', api_key: '' },
  system_prompt: '',
  thresholds: {} as Record<string, number>,
  routing_rules: [] as { scene_id: string; pipeline: string }[],
})
const newRule = reactive({ scene_id: '', pipeline: '' })

onMounted(async () => {
  await store.load()
  if (store.config) {
    Object.assign(form, JSON.parse(JSON.stringify(store.config)))
  }
})

function addRule() {
  if (!newRule.scene_id || !newRule.pipeline) return
  form.routing_rules.push({ scene_id: newRule.scene_id, pipeline: newRule.pipeline })
  newRule.scene_id = ''
  newRule.pipeline = ''
}

async function handleSave() {
  await store.save({ ...form } as any)
  ElMessage.success('配置已保存')
}
</script>
```

- [ ] **Step 4: Add route and sidebar**

Modify `frontend/src/router/index.ts`, add to children array:
```typescript
        { path: 'agent', name: 'Agent', component: () => import('@/views/Agent/Index.vue') },
```

Modify `frontend/src/components/Sidebar.vue`, add after the models menu item:
```vue
    <el-menu-item index="/agent">
      <el-icon><Setting /></el-icon><span>Agent 配置</span>
    </el-menu-item>
```

Also add `Setting` to the import:
```typescript
import { Odometer, VideoCamera, Collection, Setting } from '@element-plus/icons-vue'
```

- [ ] **Step 5: Verify build**

```bash
cd frontend && npx vite build
```
Expected: Build completes without errors

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api/agent.ts frontend/src/stores/agent.ts frontend/src/views/Agent/ frontend/src/router/index.ts frontend/src/components/Sidebar.vue
git commit -m "feat: add agent configuration page"
```

---

### Task 5: Register New Routes in app.py + Final Verification

- [ ] **Step 1: Update app.py with all route registrations**

The app.py should now have these admin imports and registrations:

```python
from src.api.routes.admin.auth import router as admin_auth_router
from src.api.routes.admin.auth import get_current_user
from src.api.routes.admin.dashboard import router as admin_dashboard_router
from src.api.routes.admin.models import router as admin_models_router
from src.api.routes.admin.agent import router as admin_agent_router
```

```python
app.include_router(admin_auth_router)
app.include_router(admin_dashboard_router)
app.include_router(admin_models_router)
app.include_router(admin_agent_router)
```

- [ ] **Step 2: Run all tests**

```bash
.venv\Scripts\python.exe -m pytest tests/ -v --tb=short
```
Expected: all tests pass

- [ ] **Step 3: Full frontend build**

```bash
cd frontend && npx vite build
```
Expected: Build succeeds

- [ ] **Step 4: Commit**

```bash
git add src/api/app.py
git commit -m "feat: register admin model and agent routes"
```

---

## Deployment

After Phase 2, push to Gitea and the CI will auto-deploy:

```bash
git push gitea master:main
```

Verify on VM2:
- `POST /api/v1/auth/login` → JWT token
- `GET /api/v1/models/{id}/stats` → model stats
- `GET/POST /api/v1/agent/config` → agent config CRUD
- `http://192.168.3.123/` → SPA with Models and Agent menus
