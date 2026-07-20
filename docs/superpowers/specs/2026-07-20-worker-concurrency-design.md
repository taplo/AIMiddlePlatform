# Worker 并发吞吐优化设计

## 问题

`src/worker.py` 的 `async for raw in queue.consume()` 单循环串行处理消息。`process_one()` 内部链：`decode → fast_path → [agent] → video_cache → db_save → ws_publish → rule_eval` 完成后才能处理下一条消息。1000+ 路摄像头下吞吐不足。

## 方案：Semaphore 并发分派 + 写操作队列解耦

```
consume loop (Semaphore N)
  ├── process_one #1 (decode → fast_path/agent → video_cache → db_queue → rule_queue)
  ├── process_one #2
  ├── process_one #3
  └── ...
       ├── video_cache  (fire-and-forget)
       ├── db_queue ──→ db_worker (BoundedSemaphore 3)
       └── rule_queue ──→ rule_worker (BoundedSemaphore 2)
```

## 组件

### 1. `Worker.__init__` 新增

- `self._semaphore = asyncio.Semaphore(max_concurrent)` — 主并发控制
- `self._db_queue = asyncio.Queue(maxsize=db_queue_size)` — DB 写缓冲
- `self._rule_queue = asyncio.Queue(maxsize=rule_queue_size)` — 规则评估缓冲
- `self._db_worker_task` / `self._rule_worker_task` — 后台消费者


### 2. `process_one()` 改造

- `_decode_frame()` 改为 `await asyncio.to_thread(_decode_frame_sync, frame_raw)` 利用线程池
- `video_cache.push()` 保持 fire-and-forget (`asyncio.create_task`)
- `_save_result()` 拆分为 `db_queue.put_nowait((task_id, camera_id, result))` + `rule_queue.put_nowait(...)`
- `ws_publish` 留在 process_one() 内（需要实时推送）

### 3. `_db_worker()` 后台协程

```python
async def _db_worker(self):
    while True:
        task_id, camera_id, result = await self._db_queue.get()
        try:
            async with AsyncSession(self.db) as session:
                ...  # 原 _save_result 的 DB 部分
                await session.commit()
        except Exception:
            logger.exception("db_worker: failed for %s", task_id)
        finally:
            self._db_queue.task_done()
```

### 4. `_rule_worker()` 后台协程

```python
async def _rule_worker(self):
    sem = asyncio.Semaphore(2)
    while True:
        task_id, camera_id, result = await self._rule_queue.get()
        async def _wrapped():
            async with sem:
                await _evaluate_rules_for_task(self.db, task_id, camera_id, result)
        asyncio.create_task(_wrapped())
        self._rule_queue.task_done()
```

### 5. `run_worker()` 改造

主循环不 await process_one，通过 `asyncio.create_task` 并发分派；信号量由 wrapper 内部管理。

```python
async def _process_with_semaphore(self, raw: str) -> None:
    async with self._semaphore:
        try:
            msg = json.loads(raw)
            await self.process_one(msg)
        except Exception:
            logger.exception("Failed to process message")

async def run_worker(...):
    worker = Worker(db)
    asyncio.create_task(worker._db_worker(), name="db-worker")
    asyncio.create_task(worker._rule_worker(), name="rule-worker")

    async for raw in queue.consume("aimp:tasks"):
        asyncio.create_task(worker._process_with_semaphore(raw))
```

## 背压策略

| 队列 | 满时行为 |
|------|----------|
| `db_queue` | `put_nowait` → QueueFull 时 fallback 到 `await asyncio.wait_for(put, timeout=5)` → 超时则 **跳过 DB 保存**，记录警告 |
| `rule_queue` | 同上，超时则 **跳过规则评估** |
| `_semaphore` | 自然阻塞 consume 循环，事件循环处理其他任务 |

## 配置变更

```yaml
# config/default.yaml 新增
worker:
  max_concurrent: 10
  db_queue_size: 200
  rule_queue_size: 200
```

## 错误处理

- DB worker：单个任务异常仅记录日志，不崩溃 worker
- Rule worker：被 asyncio.create_task 包裹，异常由事件循环捕获
- 主循环：消息 JSON 解析失败直接跳过，不影响后续消息
- 优雅退出：暂不实现 drain（K8s 下 SIGTERM 会切断连接）

## 测试策略

- `test_worker_concurrent_tasks`：同时提交 N 条消息，验证全部处理完成
- `test_worker_backpressure_db`：mock DB 写入慢，验证背压日志
- `test_worker_decode_offloaded`：验证 `_decode_frame` 在线程池执行
- 现有 `test_worker_processes_and_saves`、`test_worker_falls_through_to_agent` 不变

## 不纳入范围

- MySQL 迁移（独立优化项）
- 推理批处理（独立优化项）
- Agent 路由早期退出（独立优化项）
- 多进程 Worker 池（未来演进）
