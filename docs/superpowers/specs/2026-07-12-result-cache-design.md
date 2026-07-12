# 结果缓存/去重设计

日期: 2026-07-12
状态: 草稿
前置: docs/superpowers/specs/2026-07-10-architecture-revision-design.md
       docs/superpowers/specs/2026-07-11-verify-node-design.md

## 1. 背景

VERIFY 节点和 Agent 路径均需调用 LLM（Qwen-VL / DeepSeek-VL），而相邻帧之间场景变化极小，大量 LLM 调用返回相同结果。当前每帧都独立调用 LLM，造成：
- 不必要的 API 费用（每帧 ~0.01-0.03 元）
- 延迟增加（VERIFY 每帧 ~1-3s，Agent 路径 ~3-5s）
- Worker 吞吐受限

目标：对 VERIFY 和 Agent 路径的 LLM 调用进行缓存去重，在保证准确性的前提下跳过重复调用。

## 2. 设计

### 2.1 架构

```
                    ┌─────────────────────┐
                    │      Worker          │
                    │  ┌───────────────┐   │
                    │  │ FrameHasher   │   │
                    │  │  (pHash 8×8) │   │
                    │  └──────┬────────┘   │
                    │         ▼            │
                    │  ┌───────────────┐   │
                    │  │ ResultCache   │   │
                    │  │ (Redis 后端)   │   │
                    │  └──────┬────────┘   │
                    │         │            │
                    │    ┌────┴────┐       │
                    │    ▼        ▼        │
                    │ VERIFY   Agent      │
                    │ 节点     路径        │
                    └────┬────────┬────────┘
                         │        │
                         ▼        ▼
                      ┌──────────────┐
                      │    Redis      │
                      │ cache:*       │
                      └──────────────┘
```

### 2.2 FrameHasher

帧感知哈希，将帧图像转换为固定长度的哈希值，用于相似度比较。

```python
class FrameHasher:
    def __init__(self, hash_size: int = 8):
        self.hash_size = hash_size

    def compute(self, frame: bytes) -> str:
        """输入帧字节 → 64-bit hex hash"""
        # 1. 解码为 numpy array (RGB)
        # 2. 缩放到 hash_size × hash_size
        # 3. 转灰度
        # 4. 计算 DCT (离散余弦变换)
        # 5. 取左上角低频 8×8
        # 6. 以中位数为阈值二值化
        # 7. 拼接为 64-bit hex 字符串

    def hamming_distance(self, a: str, b: str) -> int:
        """两个 hex hash 的汉明距离"""
```

参数:
- `hash_size`: 8 (64-bit hash，小而快，适合摄像头场景)
- 相似判定阈值: `≤ 8` (64-bit 中最多 12.5% 位不同视为相似)

### 2.3 ResultCache

```python
@dataclass
class CacheResult:
    result: dict
    created_at: float
    context_hash: str

class ResultCache:
    def __init__(
        self,
        redis_client,
        ttl: int = 60,
        threshold: int = 8,
    ):
        self.redis = redis_client
        self.ttl = ttl          # 缓存 TTL (秒)
        self.threshold = threshold  # 最大 Hamming 距离

    async def get(
        self, camera_id: str, frame_hash: str,
        context_hash: str = "",
    ) -> CacheResult | None:
        """查缓存"""
        # 1. 精确匹配: GET cache:result:{camera_id}:{frame_hash}
        #    如果命中且 context 匹配 → 返回
        # 2. 模糊匹配:
        #    ZRANGEBYSCORE cache:camera:{camera_id}:hashes
        #    now-ttl ~ now → 获取近期 hash 列表
        #    对每个 hash 计算 hamming_distance
        #    找到第一个 ≤ threshold 且 context 匹配的
        # 3. 返回 None

    async def set(
        self, camera_id: str, frame_hash: str,
        result: dict, context_hash: str = "",
    ) -> None:
        """写缓存"""
        entry = CacheResult(result=result, created_at=time.time(), context_hash=context_hash)
        # 1. SET cache:result:{camera_id}:{frame_hash} json(entry) EX {ttl}
        # 2. ZADD cache:camera:{camera_id}:hashes time.time() {frame_hash}:{context_hash}
        # 3. EXPIRE cache:camera:{camera_id}:hashes {ttl}
```

### 2.4 Redis Key 设计

```
cache:result:{camera_id}:{hash_hex}
  → JSON { result, created_at, context_hash }
  TTL: 60s (可配置)

cache:camera:{camera_id}:hashes
  → Sorted Set, member = {hash_hex}:{context_hash}, score = timestamp
  TTL: 60s

cache:stats:hits
  → Counter (INCR), 总命中数

cache:stats:misses
  → Counter (INCR), 总未命中数
```

### 2.5 集成点

**VERIFY 节点** (`src/pipeline/verify_handler.py`):
```
当前:  for each detection:
          llm_result = await qwen.verify(frame, detection)
       → return llm_result

修改后:
  for each detection:
    cache_key_context = f"verify:{detection.label}:{detection.bbox_snapshot}"
    cached = await cache.get(camera_id, frame_hash, context_hash)
    if cached:
      result = cached.result
    else:
      result = await qwen.verify(frame, detection)
      await cache.set(camera_id, frame_hash, result, context_hash)
```

**Agent 路径** (`src/agent/orchestrator.py`):
```
当前:  llm_result = await client.analyze(frame, system_prompt)
       → return llm_result

修改后:
  context_hash = hash(system_prompt)  # Agent prompt 决定了行为
  cached = await cache.get(camera_id, frame_hash, context_hash)
  if cached:
    result = cached.result
  else:
    result = await client.analyze(frame, system_prompt)
    await cache.set(camera_id, frame_hash, result, context_hash)
```

注意：Agent 路径缓存需要额外考虑——当 frame 相似但 prompt 不同时（工具列表变化），应视为不同 context。因此 context_hash = sha256(system_prompt)[:16]，取前 16 位 hex 作为标识。

### 2.6 配置

```yaml
result_cache:
  enabled: true
  ttl_seconds: 60           # 缓存有效期
  hash_threshold: 8         # pHash Hamming 距离阈值
  max_candidates: 20        # 模糊匹配遍历上限
```

配置位于 `src/core/config.py`，在 `init_security` 同级或通过 `settings` 加载。

### 2.7 监控

通过 Redis 计数器暴露指标：
- `cache:stats:hits` — 启动以来累计命中数
- `cache:stats:misses` — 启动以来累计未命中数
- 命中率 = hits / (hits + misses)

可通过 `/api/v1/system/stats` 端点（已有）扩展返回。

### 2.8 缓存失效

- **TTL 自动过期**: Redis EXPIRE 处理
- **显式失效**: 预留接口 `ResultCache.invalidate(camera_id, hash_hex)`，由外部事件触发（如场景切换检测）
- **退出时不清理**: 重启后缓存逐步重建，不影响正确性

## 3. 边界情况

| 场景 | 行为 |
|------|------|
| LLM 调用失败 | 不写入缓存，下次重试 |
| Redis 不可用 | 跳过缓存，直接调用 LLM（降级） |
| pHash 碰撞 | 理论概率 < 1e-10（64-bit），可接受 |
| 摄像头画面突变（遮挡/场景切换） | 新帧 pHash 大幅变化 → cache miss → 正常调用 LLM |
| 多个 Worker 副本 | 共享 Redis，天然正确 |

## 4. 不做清单

| 功能 | 原因 |
|------|------|
| 图像 SSIM 精确匹配 | 耗时高，pHash 足以覆盖摄像头场景 |
| 缓存预热 | 无意义，缓存自动填充 |
| 持久化缓存 | 重启后重建即可，无需 RDB/AOF |
| 跨 camera 共享缓存 | 不同 camera 视角不同，共享无意义 |

## 5. 文件变更清单

| 文件 | 操作 |
|------|------|
| `src/cache/__init__.py` | 新建 |
| `src/cache/frame_hasher.py` | 新建 (FrameHasher) |
| `src/cache/result_cache.py` | 新建 (ResultCache) |
| `src/pipeline/verify_handler.py` | 修改 (集成缓存) |
| `src/agent/orchestrator.py` | 修改 (集成缓存) |
| `src/core/config.py` | 修改 (添加缓存配置) |
| `src/core/redis.py` | 修改 (导出全局 `redis_client`，供缓存和队列共用) |
| `tests/test_result_cache.py` | 新建 (单元测试) |
| `tests/test_cache_integration.py` | 新建 (集成测试) |
