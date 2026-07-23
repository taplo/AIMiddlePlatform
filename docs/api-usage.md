# AIMiddlePlatform API 使用手册

> 面向算法工程师和应用开发者的 API 接入指南。  
> 在线文档（Swagger UI）：启动服务后访问 `http://<host>:8000/docs`

---

## 目录

1. [快速开始](#快速开始)
2. [认证方式](#认证方式)
3. [核心 API](#核心-api)
   - [帧分析](#1-帧分析-apiv1analyze)
   - [任务查询](#2-任务查询-apiv1tasks)
   - [模型管理](#3-模型管理-apiv1models)
   - [路由配置](#4-路由配置-apiv1routing)
   - [配置管理](#5-配置管理-apiv1config)
   - [健康检查](#6-健康检查-apiv1health)
   - [告警管理](#7-告警管理-apiv1alerts)
   - [视频缓存](#8-视频缓存-apiv1video-cache)
4. [管理 API](#管理-api)
   - [仪表盘](#1-仪表盘)
   - [流水线管理](#2-流水线管理)
   - [日志与追踪](#3-日志与追踪)
   - [通知渠道](#4-通知渠道)
   - [API 密钥管理](#5-api-密钥管理)
   - [规则引擎](#6-规则引擎)
5. [Webhook 告警配置](#webhook-告警配置)
6. [WebSocket 实时推送](#websocket-实时推送)
7. [错误码说明](#错误码说明)
8. [模型注册与切换](#模型注册与切换)
9. [限流说明](#限流说明)

---

## 快速开始

```bash
# 1. 获取 API Key（从管理员处或环境变量配置）
export API_KEYS="default:sk-aimp-default-key-12345678:100"

# 2. 启动服务
uvicorn src.api.app:app --host 0.0.0.0 --port 8000

# 3. 发送分析请求
curl -X POST http://localhost:8000/api/v1/analyze/frame \
  -H "X-API-Key: sk-aimp-default-key-12345678" \
  -H "Content-Type: application/json" \
  -d '{
    "frame": "<base64-encoded-image>",
    "camera_id": "cam-001",
    "scene_type": "parking_lot"
  }'
```

---

## 认证方式

系统支持两种认证方式，分别用于不同的使用场景。

### API Key 认证（业务接口）

适用于摄像头帧提交、任务查询等业务场景的认证。

**请求头**：`X-API-Key: <your-api-key>`

**API Key 格式**：环境变量 `API_KEYS` 使用分号分隔多个 key：

```
API_KEYS="key_name1:sk-actual-key-1:rate_limit;key_name2:sk-actual-key-2:rate_limit"
```

- `key_name`：标识名称（仅用于管理）
- `sk-actual-key`：API Key 本身（至少 8 位）
- `rate_limit`：每秒请求数限制（可选，默认 10）

### JWT 认证（管理接口）

适用于管理后台 /admin 等接口。

1. 登录获取 token：
   ```bash
   curl -X POST http://localhost:8000/api/v1/auth/login \
     -H "Content-Type: application/json" \
     -d '{"username": "admin", "password": "<admin-password>"}'
   ```
   响应包含 `access_token`，有效期由 `JWT_EXPIRY_SECONDS` 控制。

2. 在后续请求中使用：
   ```bash
   curl -H "Authorization: Bearer <access_token>" \
     http://localhost:8000/api/v1/admin/dashboard/stats
   ```

### 无需认证的接口

以下路径可匿名访问：

| 路径 | 说明 |
|------|------|
| `GET /api/v1/analyze/ping` | 连通性探测 |
| `GET /api/v1/health` | 健康检查 |
| `GET /metrics` | Prometheus 指标 |

---

## 核心 API

### 1. 帧分析 (`/api/v1/analyze`)

#### `POST /api/v1/analyze/frame`

提交一帧图像进行分析。

**请求体**：

```json
{
  "frame": "<base64-encoded-image>",
  "camera_id": "cam-001",
  "scene_type": "parking_lot",
  "model_id": "object_detection"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `frame` | string | 是 | Base64 编码的 JPEG/PNG 图像（最大 10MB） |
| `camera_id` | string | 是 | 摄像头唯一标识 |
| `scene_type` | string | 否 | 场景类型（如 `parking_lot`、`street`、`office`） |
| `model_id` | string | 否 | 指定模型 ID，不指定则由路由自动选择 |

**查询参数**：

| 参数 | 类型 | 说明 |
|------|------|------|
| `sync` | bool | 同步模式，调试用。设为 `true` 时等待完整处理结果再返回 |

**响应**（异步模式）：

```json
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "queued"
}
```

| 状态 | 说明 |
|------|------|
| `queued` | 已加入处理队列 |
| `queued_local` | Redis 不可用，降级为内存队列 |
| `rejected` | 帧质量不合格（模糊/过暗/重复等） |
| `skipped` | 自适应采样跳过（场景变化不足） |

**响应**（同步模式 `?sync=true`）：

```json
{
  "task_id": "...",
  "path": "fast",
  "result": {
    "detections": [
      {
        "bbox": [100, 200, 300, 400],
        "label": "car",
        "confidence": 0.95
      }
    ]
  }
}
```

#### `GET /api/v1/analyze/ping`

连通性探测，无需认证。

```json
{ "ok": true, "timestamp": "2026-07-21T12:00:00" }
```

### 2. 任务查询 (`/api/v1/tasks`)

#### `GET /api/v1/tasks/{task_id}`

查询任务状态和结果。

```json
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "camera_id": "cam-001",
  "status": "completed",
  "path_taken": "fast",
  "result": { ... },
  "created_at": "...",
  "completed_at": "..."
}
```

| 状态 | 说明 |
|------|------|
| `queued` | 排队中 |
| `processing` | 处理中 |
| `completed` | 已完成 |
| `rejected` | 被拒绝（帧质量问题） |
| `failed` | 处理失败 |

### 3. 模型管理 (`/api/v1/models`)

#### `GET /api/v1/models/`

列出所有已注册模型。可选 `?status=online` 过滤。

#### `GET /api/v1/models/active`

列出当前活跃（online）模型。

#### `GET /api/v1/models/{model_id}`

查询单个模型详情。可选 `?version=1.0.0`。

#### `POST /api/v1/models/`

注册新模型。

```json
{
  "model_id": "my_custom_detector",
  "name": "自定义检测模型",
  "version": "1.0.0",
  "description": "基于 YOLOv8 的检测模型",
  "backend": "onnx",
  "tags": ["detection", "custom"],
  "cost_estimate": "low"
}
```

#### `POST /api/v1/models/{model_id}/status`

切换模型状态（online / offline / archived）。

```json
{ "version": "1.0.0", "status": "offline" }
```

#### 预置模型列表

| model_id | 名称 | 说明 |
|----------|------|------|
| `object_detection` | 目标检测 | YOLOv8n 通用目标检测 |
| `face_recognition` | 人脸识别 | 人脸检测与特征提取 |
| `license_plate` | 车牌识别 | 车牌检测与 OCR |
| `vehicle_detection` | 车辆检测 | 车辆类型分类 |
| `ocr` | 文字识别 OCR | 自然场景文字识别 |
| `person_reid` | 行人重识别 | 跨摄像头行人匹配 |
| `yolo_world` | 开放词汇检测 | 文本提示驱动的任意目标检测 |

### 4. 路由配置 (`/api/v1/routing`)

#### `POST /api/v1/routing/routes`

注册场景到流水线的映射。

```json
{ "scene_id": "parking_lot", "pipeline": "fast_pipeline" }
```

#### `DELETE /api/v1/routing/routes/{scene_id}`

删除指定场景的路由。

#### `POST /api/v1/routing/matchers/camera_id`

配置摄像头 ID 到场景的映射。

```json
{
  "mapping": {
    "cam-001": "parking_lot",
    "cam-002": "street"
  }
}
```

#### `POST /api/v1/routing/matchers/scene_type`

配置场景类型匹配规则。

#### `POST /api/v1/routing/reload`

触发路由配置热重载。

### 5. 配置管理 (`/api/v1/config`)

#### `GET /api/v1/config`

列出应用配置（脱敏后）。

#### `GET /api/v1/config/{section}`

查询指定配置节（如 `queue`、`llm`、`storage`）。

### 6. 健康检查 (`/api/v1/health`)

无需认证。

```json
{
  "status": "ok",
  "service": "aimiddleplatform",
  "version": "0.1.0",
  "uptime_seconds": 3600,
  "checks": {
    "database": { "status": "ok", "latency_ms": 2.1 },
    "redis": { "status": "ok", "latency_ms": 0.5 },
    "llm": { "status": "ok", "available": true },
    "model_registry": { "status": "ok", "models_count": 7 }
  }
}
```

| 整体状态 | 说明 |
|----------|------|
| `ok` | 所有组件正常 |
| `degraded` | 部分组件异常（如 Redis 或 LLM 不可用） |
| `error` | 数据库不可用 |

### 7. 告警管理 (`/api/v1/alerts`)

#### `GET /api/v1/alerts`

查询告警列表。支持分页和过滤参数。

#### `PUT /api/v1/alerts/{alert_id}/status`

更新告警处理状态（pending / acknowledged / resolved）。

### 8. 视频缓存 (`/api/v1/video-cache`)

#### `POST /api/v1/video-cache`

配置视频流缓存参数。

#### `DELETE /api/v1/video-cache/{stream_id}`

清除指定流的缓存。

---

## 管理 API

### 1. 仪表盘

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/admin/dashboard/stats` | 获取平台统计概览 |

### 2. 流水线管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/admin/pipelines` | 列出所有流水线 |
| GET | `/api/v1/admin/pipelines/{name}` | 查询流水线 DAG |
| POST | `/api/v1/admin/pipelines` | 创建流水线 |
| PUT | `/api/v1/admin/pipelines/{name}` | 更新流水线 |
| DELETE | `/api/v1/admin/pipelines/{name}` | 删除流水线 |

### 3. 日志与追踪

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/admin/logs` | 查询日志（支持 level、search、limit 过滤） |
| GET | `/api/v1/admin/traces` | 查询调用链追踪 |

### 4. 通知渠道

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/admin/notifications` | 列出通知渠道配置 |
| PUT | `/api/v1/admin/notifications/{channel_name}` | 更新渠道配置 |

### 5. API 密钥管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/admin/api-keys` | 列出 API 密钥 |
| POST | `/api/v1/admin/api-keys` | 创建 API 密钥 |
| DELETE | `/api/v1/admin/api-keys/{key}` | 删除 API 密钥 |

### 6. 规则引擎

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/admin/rules` | 列出规则 |
| POST | `/api/v1/admin/rules` | 创建规则 |
| GET | `/api/v1/admin/rules/{rule_id}` | 查询规则详情 |
| PUT | `/api/v1/admin/rules/{rule_id}` | 更新规则 |
| DELETE | `/api/v1/admin/rules/{rule_id}` | 删除规则 |
| GET | `/api/v1/admin/rules/bindings` | 列出规则绑定 |
| POST | `/api/v1/admin/rules/bindings` | 创建规则绑定 |
| DELETE | `/api/v1/admin/rules/bindings/{binding_id}` | 删除规则绑定 |

---

## Webhook 告警配置

平台支持将告警推送到三种即时通讯渠道。

### 支持渠道

| 渠道 | type 值 | 适配格式 |
|------|----------|----------|
| 钉钉 | `dingtalk` | Markdown 消息 |
| 企业微信 | `wechat` | Markdown 消息 |
| 飞书 | `feishu` | 消息卡片（interactive） |

### 配置方法

**方式一：管理 API**

```bash
curl -X PUT http://localhost:8000/api/v1/admin/notifications/钉钉 \
  -H "Authorization: Bearer <admin-token>" \
  -H "Content-Type: application/json" \
  -d '{
    "enabled": true,
    "config": {
      "webhook_url": "https://oapi.dingtalk.com/robot/send?access_token=xxx"
    }
  }'
```

**方式二：直接编辑配置文件**

`config/notification_channels.json`：

```json
[
  {
    "name": "DingTalk",
    "type": "dingtalk",
    "enabled": true,
    "config": { "webhook_url": "https://oapi.dingtalk.com/robot/send?access_token=xxx" }
  }
]
```

### 告警触发条件

- 帧质量检测失败（模糊、过曝、遮挡等）
- 模型推理检出异常事件（如非法入侵、物品遗留等）
- 系统组件异常（Redis 断连、数据库超时等）

---

## WebSocket 实时推送

系统通过 WebSocket 推送实时分析结果和系统事件。

### 端点

```
ws://<host>/api/v1/ws
```

### 订阅频道

连接建立后自动订阅以下频道：

| 频道 | 说明 |
|------|------|
| `ws:analysis_result` | 分析结果完成通知 |
| `ws:alert` | 实时告警推送 |
| `ws:system_event` | 系统事件（组件状态变更等） |

### 消息格式

```json
{
  "type": "analysis_result",
  "task_id": "550e8400-...",
  "camera_id": "cam-001",
  "result": { ... },
  "timestamp": "2026-07-21T12:00:00"
}
```

---

## 错误码说明

### HTTP 状态码

| 状态码 | 含义 | 典型场景 |
|--------|------|----------|
| 200 | 成功 | 请求正常处理 |
| 400 | 请求参数错误 | 缺少必填字段、帧解码失败 |
| 401 | 未认证 | 缺少或无效的 API Key / JWT |
| 403 | 权限不足 | API Key 访问管理接口 |
| 404 | 资源不存在 | 模型 ID 或任务 ID 无效 |
| 413 | 请求体过大 | 帧图片超过 10MB |
| 429 | 请求过多 | 超过 API Key 的速率限制 |
| 500 | 服务端错误 | 组件未初始化 |
| 503 | 服务不可用 | Redis 断连等基础设施问题 |

### 业务错误码（响应体中的 error/detail）

| 错误信息 | 说明 |
|----------|------|
| `Queue not initialized` | 消息队列未初始化 |
| `Frame too large (max 10MB)` | 帧数据超过 10MB 限制 |
| `Orchestrator not initialized` | Agent Orchestrator 未就绪（同步模式需要） |
| `Registry not initialized` | 模型注册表未初始化 |
| `Service unavailable (Redis): ...` | Redis 连接异常，请求降级处理 |
| `Invalid API key` | API Key 格式错误或未注册 |

---

## 模型注册与切换

### 注册新模型

```bash
curl -X POST http://localhost:8000/api/v1/models/ \
  -H "X-API-Key: <api-key>" \
  -H "Content-Type: application/json" \
  -d '{
    "model_id": "custom_detector",
    "name": "自定义检测",
    "version": "1.0.0",
    "backend": "onnx",
    "description": "业务场景专用检测模型",
    "tags": ["detection", "custom"],
    "cost_estimate": "low"
  }'
```

### 部署模型权重

ONNX 模型文件需放置在 `models/` 目录下，命名规则为 `{model_id}.onnx`：

```
models/
├── object_detection.onnx
├── face_recognition.onnx
├── license_plate.onnx
├── vehicle_detection.onnx
├── ocr.onnx
├── person_reid.onnx
└── yolo_world.onnx
```

支持通过 `scripts/download_models.py` 脚本自动下载：

```bash
# 检查模型文件状态
python scripts/download_models.py --check

# 下载缺失的模型
python scripts/download_models.py

# 强制覆盖已存在的模型
python scripts/download_models.py --force
```

### 切换模型状态

```bash
# 下架旧版本
curl -X POST http://localhost:8000/api/v1/models/object_detection/status \
  -H "X-API-Key: <api-key>" \
  -H "Content-Type: application/json" \
  -d '{"version": "1.0.0", "status": "offline"}'
```

| 状态值 | 说明 |
|--------|------|
| `online` | 在线可用（默认） |
| `offline` | 下线维护 |
| `archived` | 归档不再使用 |

### 自定义适配器

要实现自定义模型后端，继承 `ModelAdapter` 并实现 `predict()` 方法：

```python
from src.models.inference import ModelAdapter
from src.models.registry import ModelSpec

class MyAdapter(ModelAdapter):
    async def predict(self, spec: ModelSpec, input_data: dict) -> dict:
        image = input_data.get("image")
        # 自定义推理逻辑
        return {"detections": [...], "count": len(...)}
```

在 `src/api/app.py` 的 `_init_components()` 中注册：

```python
inference.register_adapter("onnx", MyAdapter())
```

---

## 限流说明

系统对每个 API Key 独立限流。

### 配置方式

在 `API_KEYS` 环境变量中指定速率（每秒请求数）：

```
API_KEYS="key_name:sk-key-123:100"
```

上述配置允许每秒最多 100 次请求。不指定时默认 10 次/秒。

### 响应头

每个响应包含当前限流状态：

| 响应头 | 说明 |
|--------|------|
| `X-RateLimit-Remaining` | 当前时间窗口剩余请求数 |

### 限流行为

超过限制时返回 HTTP 429，并包含 `Retry-After: 1` 响应头。

限流后端自动选择：
- **有 Redis 时**：滑动窗口算法，跨进程共享
- **无 Redis 时**：令牌桶算法，单进程本地限流

---

## 附录

### 环境变量速查

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `API_KEYS` | `""` | API 密钥列表（分号分隔） |
| `JWT_SECRET_KEY` | `change-me` | JWT 签名密钥 |
| `DATABASE_URL` | `sqlite+aiosqlite:///data/aimp.db` | 数据库连接串 |
| `QUEUE_REDIS_URL` | `redis://localhost:6379/0` | Redis 连接串 |
| `LLM_API_URL` | `https://api.siliconflow.cn/v1` | LLM API 地址 |
| `LLM_API_KEY` | `""` | LLM API 密钥 |
| `LLM_MODEL_NAME` | `Qwen/Qwen2.5-VL-7B-Instruct` | LLM 模型名称 |
| `S3_ENDPOINT` | `""` | MinIO/S3 存储端点 |
| `S3_ACCESS_KEY` | `minioadmin` | S3 访问密钥 |
| `S3_SECRET_KEY` | `minioadmin` | S3 访问密钥 |
| `S3_BUCKET` | `aimp-results` | S3 存储桶名 |
| `DATA_COLLECTION_ENABLED` | `false` | 启用数据采集 |
