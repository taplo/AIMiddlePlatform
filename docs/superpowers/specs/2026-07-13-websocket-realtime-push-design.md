# WebSocket 实时推送设计

日期: 2026-07-13
状态: 定稿
前置: docs/superpowers/specs/2026-07-10-architecture-revision-design.md

## 1. 背景

平台当前通过 REST API (`GET /v1/tasks/{task_id}`) 提供拉取式结果查询。摄像头数量增长到 1000+ 后，客户端持续轮询会产生大量无效请求、增加 API 负载、延迟不可控。需要 WebSocket 实时推送机制，让客户端订阅后被动接收分析结果、告警和系统事件。

## 2. 整体架构

使用 Redis Pub/Sub 作为 Worker 与 API 进程间的消息桥梁：

```
Worker 进程                        API 进程
┌──────────────┐                 ┌──────────────────────┐
│ _save_result │──publish─────→  │ Redis Pub/Sub 订阅    │
│  → DB        │  ws:* 频道     │     ↓                │
│  → Redis pub │                 │  ConnectionManager   │
└──────────────┘                 │     ↓ broadcast      │
                                 │  ┌─→ WS Client 1     │
┌──────────────┐                 │  ├─→ WS Client 2     │
│ rule_engine  │──publish─────→  │  └─→ WS Client N     │
│  → alert     │                 └──────────────────────┘
└──────────────┘
```

- Worker 负责生产消息（结果/告警写入 DB 后发布到 Redis）
- API 进程的 ConnectionManager 订阅 Redis 频道，扇出给所有 WebSocket 客户端
- 水平扩展：每个 API 副本各自订阅 Redis，独立扇出

## 3. 消息协议

### 3.1 统一封包格式

所有消息使用统一 JSON 结构，客户端通过 `type` 字段区分：

```json
{
  "type": "analysis_result | alert | system_event",
  "data": { ... },
  "timestamp": "2026-07-13T12:00:00.000Z"
}
```

### 3.2 analysis_result

```json
{
  "type": "analysis_result",
  "data": {
    "task_id": "string",
    "camera_id": "string",
    "status": "completed | failed",
    "path_taken": "fast | agent | video_cache",
    "latency_ms": 145,
    "detections": [
      {"class": "person", "confidence": 0.92, "bbox": [x1,y1,x2,y2]}
    ],
    "result": {}
  },
  "timestamp": "2026-07-13T12:00:00.000Z"
}
```

### 3.3 alert

```json
{
  "type": "alert",
  "data": {
    "alert_id": 42,
    "rule_name": "string",
    "camera_id": "string",
    "severity": "low | medium | high | critical",
    "message": "string"
  },
  "timestamp": "2026-07-13T12:00:00.000Z"
}
```

### 3.4 system_event

```json
{
  "type": "system_event",
  "event": "camera_disconnected | camera_reconnected | model_status_changed | queue_backpressure",
  "data": {
    "camera_id": "string (optional)",
    "model_id": "string (optional)",
    "status": "offline | online | error",
    "detail": "string"
  },
  "timestamp": "2026-07-13T12:00:00.000Z"
}
```

## 4. Redis 频道设计

| 频道 | 内容 | 生产者 |
|------|------|--------|
| `ws:analysis_result` | 帧分析完成结果 | Worker._save_result() |
| `ws:alert` | 规则触发的告警 | rule_engine |
| `ws:system_event` | 系统状态变更事件 | 监控协程/模型注册表 |

消息体为 JSON 序列化后的字符串（Redis Pub/Sub 要求字符串负载）。

## 5. 组件设计

### 5.1 ConnectionManager (`src/ws/manager.py`)

核心类，管理 WebSocket 连接生命周期和 Redis 订阅扇出：

- `__init__(redis_url: str)`: 初始化连接列表和 Redis 客户端
- `connect(ws: WebSocket)`: 接受 WebSocket 连接，加入列表
- `disconnect(ws: WebSocket)`: 移除断连客户端
- `_subscriber_loop()`: 后台协程，订阅 `ws:*` 频道，收到消息后调用 `_broadcast`
- `_broadcast(data: str)`: 遍历所有连接发送文本帧，捕获异常清理死连接
- `start()`: 启动订阅循环协程
- `stop()`: 关闭 Redis 订阅和连接

### 5.2 WebSocket 路由 (`src/api/routes/ws.py`)

FastAPI WebSocket endpoint：

```python
@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket, token: str = Query(...)):
    # 1. 校验 token（复用 security.py 的 JWT / API Key 验证）
    # 2. token 有效 → manager.connect(ws)
    # 3. token 无效 → ws.close(code=4001)
    # 4. 保持连接存活（接收但不处理任何消息，或用于 ping/pong）
```

### 5.3 WebSocket 认证 (`src/ws/auth.py`)

- 从 URL Query 提取 `token` 参数
- JWT Token → 调用 `security.verify_jwt_token(token)`
- API Key → 按 API Key 格式校验
- 两者都失败 → 返回 4001 关闭

### 5.4 发布工具 (`src/core/redis_client.py`)

新增 `publish(channel: str, data: dict)` 函数——序列化 data 为 JSON 后发布到指定 Redis 频道。供 Worker 和 rule_engine 调用。

## 6. 集成点

| 文件 | 改动 |
|------|------|
| `src/ws/__init__.py` | 新建模块 |
| `src/ws/manager.py` | 新建 |
| `src/ws/auth.py` | 新建 |
| `src/api/routes/ws.py` | 新建 |
| `src/api/routes/__init__.py` | 注册 ws 路由 |
| `src/api/app.py` | lifespan 启动/停止 ConnectionManager |
| `src/worker.py` | `_save_result()` 末尾 publish analysis_result |
| `src/pipeline/rule_engine.py` | create_alert() 后 publish alert |
| `src/core/redis_client.py` | 新增 publish() |
| `config/default.yaml` | 新增 websocket 配置段 |
| `tests/test_ws_manager.py` | 新增 |
| `tests/test_ws_auth.py` | 新增 |
| `tests/test_ws_integration.py` | 新增 |

## 7. 配置

```yaml
websocket:
  enabled: true
  ping_interval: 30  # 心跳间隔（秒）
  max_connections: 10000
```

## 8. 错误处理

| 场景 | 处理 |
|------|------|
| Redis 订阅断开 | ConnectionManager 自动重连（指数退避），重连期间消息丢失 |
| 客户端断连 | `_broadcast` 捕获 `WebSocketDisconnect`/`ConnectionClosed`，从列表移除 |
| 客户端发送消息 | 忽略（服务端纯推送模型） |
| 心跳超时 | 服务端每 `ping_interval` 发 ping，等待 pong；超时则断开清理 |
| 连接数超限 | 关闭最老的非活跃连接 |

## 9. 消息生产集成

### 9.1 Worker._save_result()

`_save_result()` 保存到 DB 并返回 task 记录后发布 `ws:analysis_result`。数据字段直接复用 `AnalysisResult` schema。

### 9.2 RuleEngine.create_alert()

`create_alert()` 写入 DB 后发布 `ws:alert`。数据字段直接复用 `Alert` schema。

### 9.3 系统事件

监控协程检测到摄像头断开/恢复时发布 `ws:system_event`。模型注册表在模型注册/停用/异常时发布。

## 10. 测试策略

| 测试 | 内容 |
|------|------|
| `test_ws_manager.py` (3 测试) | connect/disconnect/broadcast 正确性 |
| `test_ws_auth.py` (2 测试) | 有效 token 通过、无效 token 被拒 |
| `test_ws_integration.py` (2 测试) | 使用 TestClient 端到端测试连接建立和消息接收 |

新增 ~7 个测试。
