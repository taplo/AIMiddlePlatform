# AI 算法调度中台 — 架构修正设计

日期: 2026-07-10
状态: 定稿
前置: docs/superpowers/specs/2026-07-08-ai-algorithm-scheduling-platform-design.md

## 1. 背景

原设计文档描述了七模块、三路径的架构，但经审查发现当前实现与需求存在 11 项关键偏差，其中 Agent 路径 stub、缺少队列解耦、存储缺失为阻塞性问题。本设计在保持原设计理念的前提下，修正架构路径使其在验证阶段可落地运行，同时为生产部署预留正确扩展方向。

## 2. 整体架构

```
                   ┌───────────────────┐
                   │   Client          │
                   └────────┬──────────┘
                            │ POST /v1/analyze/frame
                            ▼
                   ┌───────────────────┐
                   │  FastAPI (API层)   │
                   │  - 认证/限流       │
                   │  - 写入 Redis      │
                   │  - 返回 task_id    │
                   │  - Admin CRUD      │
                   └────────┬──────────┘
                            │ Redis Streams
                            ▼
              ┌─────────────────────────┐
              │   Worker 进程 (独立)     │
              │  ┌─────────────────┐    │
              │  │ SceneRouter     │    │
              │  │  → 匹配         │    │
              │  ├─────┬─────┬─────┤    │
              │  │Fast │Agent│Video│    │
              │  │Path │Path │Path │    │
              │  └──┬──┴──┬──┴──┬──┘    │
              │     │     │     │       │
              │     ▼     ▼     ▼       │
              │  模型  Qwen  视频缓存    │
              │  推理  -VL               │
              └────────┬─────────────────┘
                       │ 写结果
                       ▼
              ┌──────────────────┐
              │  SQLite (验证)    │
              │  → MySQL (生产)   │
              └──────────────────┘
```

### 2.1 核心变化

| 维度 | 之前 | 之后 |
|------|------|------|
| 帧处理路径 | 同步 HTTP 推理 | 异步队列 → Worker |
| Agent 路径 | stub | 真实 Qwen-VL API |
| 存储层 | 纯内存 | SQLite / MySQL |
| 进程模型 | 单进程 | API 进程 + Worker 进程 |
| 模型部署 | 单体 | 同一镜像，不同 CMD |

### 2.2 组件职责

| 组件 | 职责 | 技术选型 | 扩缩 |
|------|------|---------|------|
| API 层 | 认证、限流、帧入队、Admin CRUD、结果查询 | FastAPI + uvicorn | 水平多副本 |
| Worker | 消息消费、场景路由、模型推理、LLM 调用、结果持久化 | `python -m src.worker` | HPA 多副本 |
| Redis | 任务队列、视频缓存环形缓冲 | Redis 7 | 独立部署 |
| 存储 | 任务/告警/配置持久化 | SQLite(验证) → MySQL(生产) | 按阶段演进 |

## 3. 三路径详细设计

### 3.1 Fast Path (快速路径)

**触发条件**: SceneRouter 匹配到已注册 Pipeline。

**流程**:
```
帧入队 → Worker 消费 → SceneRouter.resolve(frame_context)
  → 匹配 Pipeline → DAGExecutor.execute(dag, context)
    → 执行节点链
      ├─ 模型推理节点 (MODEL_INFERENCE)
      │   → 调用 InferenceOrchestrator.infer(model_id, {image})
      │   → 返回检测结果 (detections, count, inference_ms)
      └─ 【新增】VERIFY 节点
          → 过滤 conf ∈ [threshold, threshold + margin) 的检测项
          → 对每项调用 QwenVLClient.verify(检材 + 原始帧)
          → 标记为 confirmed / rejected
    → 写入 tasks 表 (path_taken="fast")
    → 状态标记 completed
```

**VERIFY 节点设计**:

```
NodeType.VERIFY = "verify"

config:
  threshold: float      # 告警阈值（默认 0.60）
  margin: float         # 校验区间宽度（默认 0.15）

行为:
  consume: 前序节点的检测结果 (detections[])
  filter: 筛选 conf ∈ [threshold, threshold + margin]
  for each 筛选项:
    prompt: f"画面中坐标{x1,y1,x2,y2}位置是否检测到{label}？仅回答是/否"
    llm_response → confirmed=true / false
  output: 原始结果 + verification[] (verified_by, verified_conf, status)
```

### 3.2 Agent Path (Agent 路径)

**触发条件**: SceneRouter 无匹配。

**流程**:
```
帧入队 → Worker 消费 → SceneRouter无匹配
  → 场景预处理（提取帧元数据：分辨率、亮度、时间戳）
  → 构造 System Prompt（含可用工具列表）
  → QwenVLClient.analyze(frame, system_prompt) → LLM 返回
  → parse LLM response → 提取工具调用意图
  → InferenceOrchestrator.infer_parallel([...]) → 执行工具
  → 合成最终结果
  → 写入 tasks 表 (path_taken="agent")
```

**QwenVLClient 改造**:

```python
# src/agent/client.py
class QwenVLClient:
    def __init__(self, api_base: str, api_key: str):
        self.api_base = api_base  # 可配置：云端 API / 本地 vLLM
        self.model = "qwen-vl"

    async def analyze(self, image: bytes, prompt: str) -> dict:
        # HTTP POST /v1/chat/completions
        # messages: [{role: "system", content: ...}, {role: "user", content: [...]}]
        pass

    async def verify(self, image: bytes, detection_info: dict) -> bool:
        # 简化版 analyze，仅用于确认/拒绝告警
        pass
```

**Tool Registry 改造**:

```python
# src/agent/tools.py
# 从 ModelRegistry 动态生成工具列表
def build_cv_tools(registry: ModelRegistry) -> list[Tool]:
    for model in registry.list_models():
        tools.append(Tool(
            name=model.model_id,
            description=model.description,
            parameters=model.input_schema,
        ))
```

### 3.3 Video Path (视频算法路径)

验证阶段保持 stub，架构预留接口。当视频缓存服务就绪后启用。

## 4. Worker 进程模型

### 4.1 入口

```
# src/worker.py (新增)
python -m src.worker
```

### 4.2 消费循环

```python
async def main():
    queue = RedisStreamQueue()          # 复用现有 src/queue/
    fast_path = FastPathHandler(...)    # 复用现有 src/routing/fast_path.py
    orchestrator = AgentOrchestrator(...) # 复用现有 src/agent/orchestrator.py
    db = init_database()                # 新增 src/core/database.py

    async for message in queue.consume("aimp:tasks"):
        context = json.loads(message)
        try:
            result = await orchestrator.process(context)
            db.save_task(Task(
                id=context["task_id"],
                path_taken=result["path"],
                result_json=result,
                status="completed",
            ))
            await queue.ack(message.id)
        except Exception as e:
            db.save_task_status(context["task_id"], "failed", str(e))
```

### 4.3 部署

同一 Docker 镜像，不同 CMD：
- `CMD ["uvicorn", "src.api.app:app"]` （API 进程）
- `CMD ["python", "-m", "src.worker"]` （Worker 进程）

## 5. 存储层设计

### 5.1 ORM 与迁移

- **ORM**: SQLAlchemy 2.0 async (`async-sqlite` / `aiomysql`)
- **迁移**: Alembic（初始化脚本 + 后续变更）
- **连接**: 配置化，切换 SQLite ↔ MySQL 仅改 `database_url`

### 5.2 表结构

```sql
CREATE TABLE tasks (
    id           TEXT PRIMARY KEY,         -- task_id uuid
    camera_id    TEXT NOT NULL,
    path_taken   TEXT NOT NULL,            -- fast|agent|verify
    status       TEXT NOT NULL DEFAULT 'queued',  -- queued|processing|completed|failed
    frame_path   TEXT,                     -- 帧存储路径（非必填）
    result_json  TEXT,                     -- 完整推理结果 JSON
    alert_count  INTEGER DEFAULT 0,
    latency_ms   INTEGER,
    error_msg    TEXT,
    created_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at   DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE alerts (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id       TEXT NOT NULL REFERENCES tasks(id),
    alert_type    TEXT NOT NULL,           -- 告警类型（如 person_intrusion）
    label         TEXT NOT NULL,           -- 目标标签（如 person）
    bbox          TEXT,                    -- [x1,y1,x2,y2] JSON
    confidence    REAL NOT NULL,           -- 模型输出置信度
    verified_by   TEXT DEFAULT 'model',    -- model|llm|none
    verified_conf REAL,                    -- LLM 验证后置信度
    status        TEXT DEFAULT 'pending',  -- confirmed|rejected|pending
    created_at    DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE pipelines (
    name         TEXT PRIMARY KEY,
    dag_json     TEXT NOT NULL,
    version      INTEGER DEFAULT 1,
    updated_at   DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE models (
    model_id     TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    version      TEXT NOT NULL,
    backend      TEXT NOT NULL DEFAULT 'onnx',
    status       TEXT DEFAULT 'online',
    description  TEXT,
    tags         TEXT,                    -- JSON array
    cost_estimate TEXT DEFAULT 'low',
    config_json  TEXT,
    updated_at   DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### 5.3 迁移路径

| 阶段 | 数据库 | 何时 |
|------|--------|------|
| 验证开发 | SQLite (`data/aimp.db`) | P0 开始 |
| Demo / 小规模 | MySQL (Docker 单实例) | P5 前后 |
| 生产 | MySQL + MinIO | 进入生产 |

## 6. API 规范

### 6.1 业务 API (/v1/)

| 方法 | 路径 | 说明 | 认证 |
|------|------|------|------|
| POST | /v1/analyze/frame | 提交单帧分析 → 返回 task_id | 可选 API Key |
| POST | /v1/analyze/stream | 注册视频流（复用现有） | 可选 API Key |
| POST | /v1/tasks/batch | 批量提交帧 | 可选 API Key |
| GET | /v1/tasks/{id}/results | 查询任务结果 | 可选 API Key |

### 6.2 管理 API (/api/v1/)

| 方法 | 路径 | 说明 | 认证 |
|------|------|------|------|
| POST | /api/v1/auth/login | 登录 → JWT | 无 |
| POST | /api/v1/auth/refresh | 刷新令牌 | JWT |
| GET | /api/v1/system/stats | 系统概览 | JWT |
| CRUD | /api/v1/models | 模型管理 | JWT |
| CRUD | /api/v1/pipelines | 流水线管理 | JWT |
| GET | /api/v1/tasks | 任务列表（新增） | JWT |
| GET | /api/v1/alerts | 告警列表（新增） | JWT |
| GET | /api/v1/logs | 日志查询 | JWT |
| GET | /api/v1/traces | 追踪查询 | JWT |
| GET/POST | /api/v1/agent/config | Agent 配置 | JWT |
| GET/POST | /api/v1/config | 系统配置 | JWT |

### 6.3 认证策略

- 管理 API: **必须** JWT（不变）
- 业务 API: **可选** API Key (`X-API-Key` header)
- 限流: token bucket 中间件，分别限制管理和业务 API

## 7. 视频缓存服务

### 7.1 设计

```python
class VideoBuffer:
    def __init__(self, camera_id: str, max_duration: int, fps: int):
        self.camera_id = camera_id
        self.frames: deque[tuple[float, np.ndarray]] = deque(maxlen=fps * max_duration)
        self.fps = fps
        self.max_duration = max_duration
```

- 每路摄像头独立 `VideoBuffer` 实例
- 配置化：`config.video_cache.default_duration` (默认 60s)
- per-stream 覆盖：注册流时可指定 `cache_duration`（最大 1800s）
- 事件触发提取：`buffer.extract_segment(before_sec, after_sec) → list[frames]`
- 验证阶段使用内存，阶段二支持 SSD 持久化

## 8. 验证阶段执行计划

### P0: 基础设施
- 新增 `src/core/database.py`（SQLAlchemy + SQLite，含 ORM 模型定义）
- 新增 `src/worker.py`（Worker 入口 + 消费循环）
- Alembic 初始化迁移

### P1: 帧路径切换
- API 层 `/v1/analyze/frame` 改为默认写队列
- Worker 消费 → 执行 Fast Path (现有 DAGExecutor 复用) → 写 SQLite
- 保留 `?sync=true` 兼容
- 新增 `GET /v1/tasks/{id}/results`

### P2: Agent 路径真实化
- `QwenVLClient` 从 stub 改为 HTTP 调用
- `CVAgent.analyze()` 真实实现（构造 prompt → 调用 LLM → 解析 → 调工具）
- `ToolRegistry` 从 ModelRegistry 动态构建

### P3: VERIFY 节点
- 新增 `NodeType.VERIFY` + executor handler
- 阈值配置参数化
- 复用 QwenVLClient.verify()

### P4: 视频缓存
- `VideoBuffer` 实现
- per-stream 配置化缓存时长
- 事件触发片段提取

### P5: API 规范化 + 前端对齐
- API 路径规范
- 新增告警 / 任务查询端点
- 前端相应的列表页面

### P6: 安全层
- API Key 认证中间件（业务 API）
- token bucket 限流
- 配置化管理

## 9. 不做清单 (Out of Scope)

| 功能 | 不做原因 | 预计 |
|------|---------|------|
| WebSocket 实时推流 | 验证阶段轮询足矣 | P5+ |
| MinIO 大对象存储 | SQLite 够装验证期结果 | 生产前 |
| K8s 独立部署 | 验证阶段单机够用 | 生产前 |
| 场景预处理器(YOLO-World) | 复杂度高，验证后再投入 | P2+ |
| 多轮 Agent 交互 | 一次调用足矣 | 生产后 |
| 联邦学习 / 蒸馏 | 核心能力未通，勿过早优化 | 远期 |
| 分库分表 | 单库能撑 | 万路级 |
| vLLM 本地集群 | 复用云端 Qwen-VL | 按需 |

## 10. 架构合规检查

| 需求维度 | 原状态 | 修正后 | 合规 |
|---------|--------|--------|------|
| Agent 路径 | stub | 真实 Qwen-VL | ✅ |
| 队列解耦 | 框架有但没连 | Redis → Worker | ✅ |
| 模型独立部署 | 单体 | 同一镜像不同进程 | ⚠️ 验证阶段可接受 |
| 持久化 | 无 | SQLite → MySQL | ✅ |
| 告警校验 | 无（新增需求） | VERIFY 节点 | ✅ |
| 视频缓存 | stub | 可配置缓存 | ✅ |
| 认证限流 | 无 | API Key + 限流 | ✅ |
| 前端后端对齐 | 前端 > 后端 | P5 修复落差 | ✅ |
| 三路径 | 2/3 不完整 | P0-P4 逐步补齐 | ✅ |
| 存储 schema | 无 | SQLAlchemy + Alembic | ✅ |

## 11. 风险评估

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|---------|
| Redis 不可用导致全链路阻塞 | 低 | 高 | Worker 启动检测 + 健康检查；`?sync=true` 旁路 |
| Qwen-VL API 延迟或不可用 | 中 | 中 | Agent 路径超时降级到 Fast Path；VERIFY 限时可跳过 |
| Worker 处理跟不上帧生产 | 中 | 中 | Worker HPA + Redis Stream 背压；Consumer Group 自动 rebalance |
| SQLite 写入竞争 | 低 | 中 | 默认 WAL 模式；单 Worker 串行写 |
| 帧 base64 体积大耗尽内存 | 低 | 高 | 帧大小限制 + 压缩配置；Worker 内逐帧处理不累积 |
