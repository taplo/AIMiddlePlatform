# 架构修复设计 — AI 算法调度中台

日期: 2026-07-13
状态: 草案

## 概述

大重构一次性修复，涵盖 6 个工作包、26 个已识别的架构问题。核心动因：Agent 层（LLM 决策大脑）存在 3 个致命运行时 bug，会无声地破坏 DAG 管线执行，且配置/初始化系统不支持标准的生产部署方式。

---

## WP1: Agent 层修复

### 问题

10 个问题，其中 3 个致命：

| # | 问题 | 文件 | 严重度 |
|---|------|------|--------|
| 1 | DAG Executor 对所有 handler 使用 `asyncio.to_thread()` — async handler 静默不执行 | `executor.py:49` | 🔴 |
| 2 | Worker 缺少 AGGREGATE + CONDITION handler 注册 | `worker.py:136-137` | 🔴 |
| 3 | verify_handler 在线程池中使用 `asyncio.run()` + 同步 Redis | `verify_handler.py:115` | 🔴 |
| 4 | AgentOrchestrator 双重执行 fast path | `orchestrator.py:28` | 🟡 |
| 5 | 两套并行的 pHash 缓存（async + sync） | `result_cache.py` vs `verify_handler.py` | 🟡 |
| 6 | 工具参数（base64）与 adapter 预期（numpy）不匹配 | `tools.py:44` | 🟡 |
| 7 | 无 HTTP 客户端连接池管理 | `client.py:71` | 🟡 |
| 8 | DeepSeekVLClient API 格式兼容性存疑 | `client.py:165` | 🟡 |
| 9 | SYSTEM_PROMPT 与 tool_calls 的 content 不协调 | `agent.py:120` | 🟡 |
| 10 | VERIFY 对每个检测框串行调用 LLM | `verify_handler.py:72-142` | 🟡 |

### 设计

**1a — DAG Executor async/sync 分派**

使用 `inspect.iscoroutinefunction()` 自动检测。async handler 在事件循环中直接 `await`；sync handler 通过 `asyncio.to_thread()` 在线程池执行。

```python
# executor.py
import inspect

async def execute(self, dag, context):
    ...
    for nid in ready:
        handler = self._handlers[node.node_type]
        input_data = {dep: results[dep] for dep in dag.nodes[nid].depends_on}
        if inspect.iscoroutinefunction(handler):
            results[nid] = await handler(context, input_data, dag.nodes[nid].config)
        else:
            results[nid] = await asyncio.to_thread(handler, context, input_data, dag.nodes[nid].config)
```

**1b — verify_handler 异步改造**

从同步函数（+ `asyncio.run()` + 同步 Redis 客户端）改为纯异步函数。用统一的 `ResultCache` 替代自建同步缓存。用 `asyncio.gather()` 并行化 LLM 验证调用。

```python
# verify_handler.py — 重构后
async def verify_handler(context, input_data, node_config) -> dict:
    threshold = node_config.get("verify_threshold", 0.5)
    margin = node_config.get("verify_margin", 0.3)
    detections = input_data.get("detections", [])
    frame_b64 = context.get("frame", "")
    if not frame_b64 or not detections:
        return {"detections": detections, "verification_count": 0}

    frame = _decode_frame(frame_b64)
    if frame is None:
        return {"detections": detections, "verification_count": 0, "error": "decode_failed"}

    client = _get_verify_client()
    cache = await _get_result_cache()
    hasher = _get_verify_hasher()
    frame_hash = hasher.compute(base64.b64decode(frame_b64))

    tasks = []
    for det in detections:
        conf = det.get("confidence", 0)
        if threshold <= conf < (threshold + margin):
            cache_key = f"verify:{det.get('label', '')}"
            cached = await cache.get(context.get("camera_id", ""), frame_hash, cache_key)
            if cached:
                det["verified"] = cached.result.get("verified", False)
                det["verification_reason"] = cached.result.get("reason", "")
                continue
            tasks.append(_verify_one_detection(client, cache, frame, det, frame_hash, cache_key))
        else:
            det["verified"] = True

    if tasks:
        await asyncio.gather(*tasks)
    return {"detections": detections, "verification_count": len(tasks)}
```

**1c — Worker 补充 handler 注册**

在 worker 的 `_init_fast_path()` 中添加缺失的 handler：

```python
executor.register_handler(NodeType.MODEL_INFERENCE, _inference_handler)
executor.register_handler(NodeType.VERIFY, verify_handler)
executor.register_handler(NodeType.AGGREGATE, aggregate_handler)    # 新增
executor.register_handler(NodeType.CONDITION, condition_handler)    # 新增
```

**1d — 消除 AgentOrchestrator 中的重复 fast path**

```python
class AgentOrchestrator:
    async def process(self, frame_context, image_data=None):
        # 调用方已尝试过 fast path — 直接走 agent
        if image_data:
            return await self.agent.analyze_with_image(frame_context, image_data)
        return await self.agent.analyze(frame_context)
```

**1e — 工具参数管线**

在 `execute_tool()` 中解码 base64 → numpy array，再传给模型 adapter。

**1f — HTTP 客户端生命周期**

给 `QwenVLClient` 添加 `aclose()`。CVAgent 和 verify_handler 共享同一个客户端实例。

### 改动文件

- `src/pipeline/executor.py`
- `src/pipeline/verify_handler.py`
- `src/worker.py`
- `src/agent/orchestrator.py`
- `src/agent/agent.py`
- `src/agent/tools.py`
- `src/agent/client.py`

---

## WP2: 配置系统统一

### 问题

- 两套并行配置系统（`Settings` + `ConfigManager`），均只读 YAML
- 都不读环境变量（标准 Docker/K8s 注入方式）
- `ConfigManager` 的热重载功能未使用
- `production.yaml` 使用了 `yaml.safe_load` 不展开的 `${VAR:-default}` 语法

### 设计

**2a — 统一为单 `Settings` 类**

三层优先级：环境变量 → production.yaml → default.yaml

关键设计决策：
- YAML 文件保留在 Docker 镜像中作为出货默认值
- 运行时通过环境变量覆盖（无需重 build）
- `_ENV_KEY_MAP` 提供配置键到环境变量名的显式映射
- 移除 `ConfigManager`，将其使用者迁移到 `Settings`
- 不引入新依赖（不用 pydantic-settings）

**2b — 环境变量映射**

```python
_ENV_KEY_MAP = {
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
    "websocket.max_connections": "WS_MAX_CONNECTIONS",
}
```

### 改动文件

- `src/core/config.py` — 重写
- `src/core/config_manager.py` — 删除
- `src/api/routes/config_routes.py` — 迁移到统一 Settings
- 6 处 import 引用：`from src.core.config_manager import config_manager` → `from src.core.config import settings`

---

## WP3: 初始化与依赖注入重构

### 问题

- 5 个 route 模块各自存储 `_session_factory` 模块级全局变量，在 `app.py lifespan()` 中手工注册
- Worker 和 API 重复约 80 行初始化代码（pipeline 注册、DAG handler、模型设置）
- 新增一个需要 DB 的路由需要改 3 个文件

### 设计

**3a — 集中式 DB 依赖注入**

```python
# src/api/deps.py (新增)
from collections.abc import AsyncIterator
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

_session_factory: async_sessionmaker[AsyncSession] | None = None

def init_session_factory(factory):
    global _session_factory
    _session_factory = factory

async def get_db() -> AsyncIterator[AsyncSession]:
    if _session_factory is None:
        raise RuntimeError("数据库未初始化")
    async with _session_factory() as session:
        yield session
```

路由模块使用 `Depends(get_db)` 替代模块级全局变量：

```python
@router.get("/tasks")
async def list_tasks(session: AsyncSession = Depends(get_db)):
    ...
```

**3b — 共享初始化**

```python
# src/pipeline/shared_init.py (新增)
def register_default_pipelines(registry: PipelineRegistry):
    """API 和 Worker 共用"""

def register_dag_handlers(executor: DAGExecutor):
    """API 和 Worker 共用"""
    executor.register_handler(NodeType.MODEL_INFERENCE, inference_handler)
    executor.register_handler(NodeType.VERIFY, verify_handler)
    executor.register_handler(NodeType.AGGREGATE, aggregate_handler)
    executor.register_handler(NodeType.CONDITION, condition_handler)
```

### 改动文件

- `src/api/deps.py` — 新增
- `src/pipeline/shared_init.py` — 新增
- `src/api/app.py` — 使用 `get_db` 初始化 + 共享初始化
- `src/worker.py` — 使用共享初始化
- `src/api/routes/tasks.py` — 迁移到 `Depends(get_db)`
- `src/api/routes/alerts.py` — 迁移到 `Depends(get_db)`
- `src/api/routes/analyze.py` — 迁移到 `Depends(get_db)`
- `src/api/routes/admin_rules.py` — 迁移到 `Depends(get_db)`

---

## WP4: 缓存与持久化层统一

### 问题

- 两套独立的 pHash 缓存：`ResultCache`（异步，CVAgent 使用）和 verify_handler 自建的同步缓存
- `redis_client.py` 没有优雅降级或重试逻辑

### 设计

**4a — 移除 verify_handler 同步缓存**

替换为统一的 `ResultCache`。WP1 的 verify_handler 异步改造自然实现此目标。

**4b — Redis 客户端重试 + 优雅降级**

`get_redis()` 增加连接重试和退避。Worker 的 Redis 依赖用 try/except 包裹，失败时记录警告而非崩溃。

### 改动文件

- `src/pipeline/verify_handler.py` — 使用 ResultCache（WP1 已覆盖）
- `src/core/redis_client.py` — 增加重试
- `src/worker.py` — Redis 优雅降级

---

## WP5: 资源管理

### 问题

- VideoRingBuffer 存储原始 numpy 帧 — 1000 路摄像头 × 30 秒 ≈ 27GB 内存
- ONNX 模型文件打包进 Docker 镜像
- 推理会话无限制

### 设计

**5a — 视频缓冲：压缩存储 + 全局内存上限**

将 `CachedFrame` 中的 `np.ndarray` 替换为 JPEG bytes（~18 倍内存缩减）。添加 `_total_memory` 全局计数器，所有摄像头合计上限 512MB。

**5b — 模型存储：优先使用挂载卷**

运行时下载的模型存储到挂载卷（`/app/models`）。Dockerfile 仅保留默认 YOLOv8n。`ensure_model()` 优先检查挂载路径，再回退到镜像内建路径。

**5c — 推理会话：LRU 淘汰上限**

`InferenceOrchestrator` 限制并发会话上限为 5（可配置）。达到上限时 LRU 淘汰。

### 改动文件

- `src/ingestion/video_cache.py`
- `src/models/inference.py`
- `src/models/adapters/downloader.py`

---

## WP6: 安全与 API 规范化

### 问题

- 4 种不同 API 路径前缀（`/`、`/v1/`、`/api/v1/`、`/ws`）
- 默认凭据 `admin:admin123`
- 速率限制器内存态，重启即丢失

### 设计

**6a — 路由前缀统一**

所有路由归到 `/api/v1/` 下。nginx 从 4 条 location 规则简化为 1 条。

涉及的前缀变更：

| 当前 | 新路径 | 模块 |
|------|--------|------|
| `/health` | `/api/v1/health` | `routes/health.py` |
| `/v1/analyze/frame` | `/api/v1/analyze/frame` | `routes/analyze.py` |
| `/v1/tasks` | `/api/v1/tasks` | `routes/tasks.py` |
| `/v1/models` | `/api/v1/models` | `routes/models.py` |
| `/v1/routing/routes` | `/api/v1/routing/routes` | `routes/routing.py` |
| `/v1/config` | `/api/v1/config` | `routes/config_routes.py` |
| `/v1/video-cache` | `/api/v1/video-cache` | `routes/video_cache.py` |
| `/v1/alerts` | `/api/v1/alerts` | `routes/alerts.py` |
| `/v1/admin/api-keys` | `/api/v1/admin/api-keys` | `routes/api_keys.py` |
| `/v1/analyze/stream` | `/api/v1/analyze/stream` | `routes/ingest.py` |
| `/ws` | `/api/v1/ws` | `routes/ws.py` |

**6b — 凭据强化**（已推迟，当前迭代不实施）

**6c — Redis 后端速率限制**

`RateLimiter` 在有 Redis 时使用 Redis（K8s 多副本），否则回退到本地 `TokenBucket`。

### 改动文件

- `src/api/routes/health.py` — 前缀改为 `/api/v1`
- 所有 route 模块 prefix — 审计并统一
- `deploy/nginx.conf` — 单条 location
- `src/api/routes/admin/auth.py` — 自动生成密码
- `src/core/security.py` — Redis 后端速率限制

---

## 迁移策略

全部 6 个工作包以**一次性大重构**提交。原因：
- WP1 各修复相互依赖（executor 分派 → verify_handler 异步 → 缓存统一）
- WP2（配置）是 WP3（DI）干净实现的前提
- WP3 与 WP1、WP4 涉及大量相同文件
- WP5 和 WP6 相对独立但小到可以包含

**合并前检查清单：**
1. 全部现有 304 个测试通过（无回归）
2. 新增 executor async/sync 分派测试
3. 新增 verify_handler 异步 + 并行 LLM 测试
4. 手动验证：health 端点返回 200
5. 手动验证：含 CONDITION 节点的 DAG 执行规则引擎

---

## 文件汇总

| 操作 | 数量 | 示例 |
|------|------|------|
| 新增文件 | 3 | `deps.py`、`shared_init.py` |
| 修改文件 | ~20 | `executor.py`、`verify_handler.py`、`worker.py`、`agent.py`、`orchestrator.py`、`tools.py`、`client.py`、`config.py`、`config_routes.py`、`app.py`、`tasks.py`、`alerts.py`、`analyze.py`、`admin_rules.py`、`redis_client.py`、`video_cache.py`、`inference.py`、`downloader.py`、`health.py`、`auth.py`、`security.py`、`nginx.conf` |
| 删除文件 | 1 | `config_manager.py` |
