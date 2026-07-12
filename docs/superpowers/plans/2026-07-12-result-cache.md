# 结果缓存/去重 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Redis-backed pHash result cache to skip duplicate LLM calls for adjacent frames in VERIFY node and Agent path.

**Architecture:** `FrameHasher` computes 64-bit DCT-based perceptual hash; `ResultCache` (async, for Agent path) stores/retrieves LLM results in Redis keyed by `(camera_id, hash_hex)` with TTL and fuzzy matching; VERIFY handler (sync thread-pool) uses a sync Redis wrapper with the same key schema.

**Tech Stack:** Python 3.12, redis-py (sync + async), OpenCV, numpy, FastAPI

**Key constraint:** VERIFY handler runs in a thread pool (`asyncio.to_thread`) — cannot share async Redis client directly. Solution: VERIFY uses sync `redis.Redis` helper; Agent path uses async `ResultCache` with `redis.asyncio.Redis`. Same key schema, no event-loop conflicts.

## Global Constraints

- All async functions use `asyncio`
- Async Redis client shared via `src/core/redis_client.py` (module-level singleton `get_redis()`)
- Sync Redis client created locally per-module for thread-pool contexts
- pHash uses 8×8 DCT-based perceptual hash (64-bit hex)
- Hamming distance threshold defaults to 8 (12.5% bit difference)
- Cache TTL defaults to 60s
- Config follows existing YAML pattern at `config/default.yaml`
- Tests use `pytest-asyncio` with `pytest.mark.asyncio` for async tests

---

### Task 1: Shared Async Redis Client

**Files:**
- Create: `src/core/redis_client.py`
- Modify: `src/queue/redis_streams.py`

**Interfaces:**
- Consumes: `settings` from `src.core.config`
- Produces: `get_redis() -> aioredis.Redis` (shared singleton, async)
            `close_redis() -> None` (shutdown cleanup, async)

- [ ] **Step 1: Create `src/core/redis_client.py`**

```python
import logging

import redis.asyncio as aioredis

from src.core.config import settings

logger = logging.getLogger(__name__)

_redis: aioredis.Redis | None = None


async def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        redis_url = settings.get("queue.redis_url", "redis://localhost:6379/0")
        _redis = await aioredis.from_url(redis_url)
        logger.info("shared Redis client connected to %s", redis_url)
    return _redis


async def close_redis() -> None:
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None


async def ping() -> bool:
    try:
        r = await get_redis()
        return await r.ping()
    except Exception:
        return False
```

- [ ] **Step 2: Simplify `RedisStreamQueue` in `src/queue/redis_streams.py`**

Replace internal `_ensure_redis` with delegation to the shared client:

```python
from src.core.redis_client import get_redis

class RedisStreamQueue(FrameQueue):
    def __init__(self) -> None:
        self._consumer_group = settings.get("queue.consumer_group", "ingestion_workers")
        self._consumer_id = f"worker-{id(self)}"

    async def _ensure_redis(self) -> aioredis.Redis:
        return await get_redis()

    # rest unchanged ...
```

- [ ] **Step 3: Run existing tests**

```bash
$env:AIMPLATFORM_ENV='test'; $env:LOG_LEVEL='ERROR'; uv run pytest --ignore=models/test_inference.py -v
```

Expected: all still pass (imports resolve, same API)

- [ ] **Step 4: Commit**

```bash
git add src/core/redis_client.py src/queue/redis_streams.py
git commit -m "feat: shared async Redis client via redis_client.py"
```

---

### Task 2: FrameHasher

**Files:**
- Create: `src/cache/__init__.py`
- Create: `src/cache/frame_hasher.py`
- Test: `tests/test_frame_hasher.py`

**Interfaces:**
- `FrameHasher.compute(frame: bytes) -> str` — returns 16-char hex (64-bit pHash)
- `FrameHasher.hamming_distance(a: str, b: str) -> int` — bits differing

- [ ] **Step 1: Create `src/cache/__init__.py`** (empty)

- [ ] **Step 2: Write failing test `tests/test_frame_hasher.py`**

```python
import pytest
import numpy as np
from src.cache.frame_hasher import FrameHasher


def test_compute_returns_hex_string() -> None:
    hasher = FrameHasher()
    fake_frame = np.random.randint(0, 256, (480, 640, 3), dtype=np.uint8).tobytes()
    result = hasher.compute(fake_frame)
    assert isinstance(result, str)
    assert len(result) == 16


def test_similar_frames_small_distance() -> None:
    hasher = FrameHasher()
    base = np.zeros((100, 100, 3), dtype=np.uint8)
    hash_a = hasher.compute(base.tobytes())
    similar = base.copy()
    similar[5, 5] = [1, 1, 1]
    hash_b = hasher.compute(similar.tobytes())
    assert hasher.hamming_distance(hash_a, hash_b) <= 4


def test_different_frames_large_distance() -> None:
    hasher = FrameHasher()
    black = np.zeros((100, 100, 3), dtype=np.uint8)
    white = np.full((100, 100, 3), 255, dtype=np.uint8)
    dist = hasher.hamming_distance(
        hasher.compute(black.tobytes()), hasher.compute(white.tobytes())
    )
    assert dist >= 20


def test_hamming_distance_identity() -> None:
    hasher = FrameHasher()
    assert hasher.hamming_distance("abcdef1234567890", "abcdef1234567890") == 0
```

- [ ] **Step 3: Run to verify failure**

```bash
$env:AIMPLATFORM_ENV='test'; $env:LOG_LEVEL='ERROR'; uv run pytest tests/test_frame_hasher.py -v --ignore=models/test_inference.py
```

Expected: ImportError for `src.cache.frame_hasher`

- [ ] **Step 4: Create `src/cache/frame_hasher.py`**

```python
import numpy as np
import cv2


class FrameHasher:
    def __init__(self, hash_size: int = 8):
        self.hash_size = hash_size

    def compute(self, frame: bytes) -> str:
        arr = np.frombuffer(frame, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
        if img is None:
            raise ValueError("cannot decode frame bytes")
        resized = cv2.resize(img, (self.hash_size, self.hash_size))
        dct = cv2.dct(np.float32(resized))
        dct_low = dct[:self.hash_size, :self.hash_size]
        median = np.median(dct_low)
        bits = (dct_low > median).flatten()
        hex_str = "".join("1" if b else "0" for b in bits)
        return hex(int(hex_str, 2))[2:].zfill(16)

    def hamming_distance(self, a: str, b: str) -> int:
        if a == b:
            return 0
        int_a = int(a, 16)
        int_b = int(b, 16)
        return (int_a ^ int_b).bit_count()
```

- [ ] **Step 5: Run to verify passes**

```bash
$env:AIMPLATFORM_ENV='test'; $env:LOG_LEVEL='ERROR'; uv run pytest tests/test_frame_hasher.py -v --ignore=models/test_inference.py
```

Expected: 4 passed

- [ ] **Step 6: Commit**

```bash
git add src/cache/ tests/test_frame_hasher.py
git commit -m "feat: FrameHasher with DCT-based perceptual hash"
```

---

### Task 3: Async ResultCache (for Agent path)

**Files:**
- Create: `src/cache/result_cache.py`
- Test: `tests/test_result_cache.py`

**Interfaces:**
- `ResultCache.__init__(redis_client, ttl=60, threshold=8, max_candidates=20)`
- `async ResultCache.get(camera_id, frame_hash, context_hash="") -> CacheResult | None`
- `async ResultCache.set(camera_id, frame_hash, result, context_hash="") -> None`
- `async ResultCache.get_stats() -> dict`

Redis key schema:
- `cache:result:{camera_id}:{hash_hex}` → JSON, EX ttl
- `cache:camera:{camera_id}:hashes` → Sorted Set, EX ttl
- `cache:stats:hits` / `cache:stats:misses` → Counter

- [ ] **Step 1: Write failing test `tests/test_result_cache.py`**

```python
import pytest
import json
import time
from unittest.mock import AsyncMock

from src.cache.result_cache import ResultCache, CacheResult


@pytest.mark.asyncio
async def test_cache_miss_returns_none() -> None:
    mock_redis = AsyncMock()
    mock_redis.get.return_value = None
    cache = ResultCache(mock_redis)
    result = await cache.get("cam-1", "abcd" * 4)
    assert result is None
    mock_redis.incr.assert_called_once_with("cache:stats:misses")


@pytest.mark.asyncio
async def test_cache_exact_hit() -> None:
    mock_redis = AsyncMock()
    entry = CacheResult(result={"answer": 42}, created_at=time.time(), context_hash="")
    mock_redis.get.return_value = json.dumps({
        "result": {"answer": 42},
        "created_at": entry.created_at,
        "context_hash": "",
    }).encode()
    cache = ResultCache(mock_redis, threshold=0)
    result = await cache.get("cam-1", "abcd" * 4)
    assert result is not None
    assert result.result == {"answer": 42}
    mock_redis.incr.assert_called_once_with("cache:stats:hits")


@pytest.mark.asyncio
async def test_cache_set_stores_entry() -> None:
    mock_redis = AsyncMock()
    cache = ResultCache(mock_redis)
    await cache.set("cam-1", "abcd" * 4, {"answer": 42}, "ctx")
    assert mock_redis.set.called
    assert mock_redis.zadd.called
    assert mock_redis.expire.called


@pytest.mark.asyncio
async def test_cache_fuzzy_hit() -> None:
    mock_redis = AsyncMock()
    mock_redis.get.side_effect = [
        None,
        json.dumps({
            "result": {"answer": 42},
            "created_at": time.time(),
            "context_hash": "ctx",
        }).encode(),
    ]
    similar_hash = "abcd1234abcd1234"
    mock_redis.zrangebyscore.return_value = [f"{similar_hash}:ctx".encode()]
    cache = ResultCache(mock_redis, threshold=8)
    result = await cache.get("cam-1", "abcd1234abcd1235", "ctx")
    assert result is not None
    assert result.result == {"answer": 42}


@pytest.mark.asyncio
async def test_get_stats() -> None:
    mock_redis = AsyncMock()
    mock_redis.get.side_effect = [None]
    mock_redis.zrangebyscore.return_value = []
    cache = ResultCache(mock_redis)
    await cache.get("cam-1", "abcd" * 4)
    await cache.get("cam-2", "1234" * 4)
    stats = await cache.get_stats()
    assert stats["misses"] == 2
```

- [ ] **Step 2: Run to verify failure**

```bash
$env:AIMPLATFORM_ENV='test'; $env:LOG_LEVEL='ERROR'; uv run pytest tests/test_result_cache.py -v --ignore=models/test_inference.py
```

Expected: ImportError

- [ ] **Step 3: Create `src/cache/result_cache.py`**

```python
import json
import time
import logging
from dataclasses import dataclass, asdict
from typing import Any


logger = logging.getLogger(__name__)


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
        max_candidates: int = 20,
    ):
        self.redis = redis_client
        self.ttl = ttl
        self.threshold = threshold
        self.max_candidates = max_candidates

    async def get(
        self,
        camera_id: str,
        frame_hash: str,
        context_hash: str = "",
    ) -> CacheResult | None:
        exact_key = f"cache:result:{camera_id}:{frame_hash}"
        raw = await self.redis.get(exact_key)
        if raw:
            try:
                data = json.loads(raw)
                if data.get("context_hash", "") == context_hash:
                    await self.redis.incr("cache:stats:hits")
                    return CacheResult(**data)
            except (json.JSONDecodeError, TypeError):
                pass

        from src.cache.frame_hasher import FrameHasher
        hasher = FrameHasher()

        candidates = await self.redis.zrangebyscore(
            f"cache:camera:{camera_id}:hashes",
            time.time() - self.ttl,
            time.time(),
            start=0,
            num=self.max_candidates,
        )
        for member in candidates:
            if isinstance(member, bytes):
                member = member.decode()
            parts = member.split(":", 1)
            if len(parts) < 2:
                continue
            cand_hash, cand_ctx = parts
            if cand_ctx != context_hash:
                continue
            dist = hasher.hamming_distance(frame_hash, cand_hash)
            if dist <= self.threshold:
                hit_raw = await self.redis.get(
                    f"cache:result:{camera_id}:{cand_hash}"
                )
                if hit_raw:
                    try:
                        data = json.loads(hit_raw)
                        await self.redis.incr("cache:stats:hits")
                        return CacheResult(**data)
                    except (json.JSONDecodeError, TypeError):
                        pass

        await self.redis.incr("cache:stats:misses")
        return None

    async def set(
        self,
        camera_id: str,
        frame_hash: str,
        result: dict,
        context_hash: str = "",
    ) -> None:
        entry = CacheResult(
            result=result,
            created_at=time.time(),
            context_hash=context_hash,
        )
        exact_key = f"cache:result:{camera_id}:{frame_hash}"
        await self.redis.set(exact_key, json.dumps(asdict(entry)), ex=self.ttl)
        camera_set_key = f"cache:camera:{camera_id}:hashes"
        await self.redis.zadd(
            camera_set_key, {f"{frame_hash}:{context_hash}": time.time()}
        )
        await self.redis.expire(camera_set_key, self.ttl)

    async def get_stats(self) -> dict:
        hits = int(await self.redis.get("cache:stats:hits") or 0)
        misses = int(await self.redis.get("cache:stats:misses") or 0)
        total = hits + misses
        return {
            "hits": hits,
            "misses": misses,
            "total": total,
            "hit_rate": round(hits / total, 4) if total > 0 else 0.0,
        }
```

- [ ] **Step 4: Run tests**

```bash
$env:AIMPLATFORM_ENV='test'; $env:LOG_LEVEL='ERROR'; uv run pytest tests/test_result_cache.py -v --ignore=models/test_inference.py
```

Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add src/cache/result_cache.py tests/test_result_cache.py
git commit -m "feat: async ResultCache with Redis backend and fuzzy matching"
```

---

### Task 4: VERIFY Handler Cache Integration (Sync)

**Files:**
- Modify: `src/pipeline/verify_handler.py`
- Test: `tests/test_verify_handler.py` (extend, or `test_verify_cache.py`)

**Context:** `verify_handler` is a sync function called via `asyncio.to_thread` (runs in thread pool). It already uses `asyncio.run(client.verify(...))` for LLM calls. For Redis cache, we use a sync `redis.Redis` client to avoid event-loop nesting issues, with the same key schema as ResultCache.

- [ ] **Step 1: Add sync cache helpers to `verify_handler.py`**

```python
import json
import base64
import logging
import asyncio
import time

import cv2
import numpy as np

logger = logging.getLogger(__name__)

_verify_client = None
_verify_cache = None
_verify_hasher = None


def _get_verify_client():
    global _verify_client
    if _verify_client is None:
        from src.agent.client import QwenVLClient
        _verify_client = QwenVLClient()
    return _verify_client


def _get_verify_cache():
    global _verify_cache
    if _verify_cache is None:
        import redis as sync_redis
        from src.core.config import settings
        redis_url = settings.get("queue.redis_url", "redis://localhost:6379/0")
        _verify_cache = sync_redis.from_url(redis_url)
    return _verify_cache


def _get_verify_hasher():
    global _verify_hasher
    if _verify_hasher is None:
        from src.cache.frame_hasher import FrameHasher
        _verify_hasher = FrameHasher()
    return _verify_hasher
```

- [ ] **Step 2: Modify the detection loop to check cache**

Replace the `asyncio.run(client.verify(...))` block (lines 59-68) with:

```python
            try:
                context_str = f"verify:{det.get('label', '')}"
                cache = _get_verify_cache()
                hasher = _get_verify_hasher()
                frame_hash = hasher.compute(raw)
                exact_key = f"cache:result:{context.get('camera_id', '')}:{frame_hash}"
                cached = cache.get(exact_key)
                if cached:
                    cached_data = json.loads(cached)
                    entry_ctx = cached_data.get("context_hash", "")
                    if entry_ctx == context_str:
                        result = cached_data["result"]
                        det["verified"] = result.get("verified", False)
                        if result.get("corrected_label"):
                            det["corrected_label"] = result["corrected_label"]
                        det["verification_reason"] = result.get("reason", "")
                        det["verification_cache_hit"] = True
                        verified_detections.append(det)
                        v_count += 1
                        continue

                result = asyncio.run(client.verify(crop_bytes, det.get("label", ""), conf))
                det["verified"] = result.get("verified", False)
                if result.get("corrected_label"):
                    det["corrected_label"] = result["corrected_label"]
                det["verification_reason"] = result.get("reason", "")

                cache_entry = json.dumps({
                    "result": result,
                    "created_at": time.time(),
                    "context_hash": context_str,
                })
                cache.set(exact_key, cache_entry, ex=60)
                camera_set_key = f"cache:camera:{context.get('camera_id', '')}:hashes"
                cache.zadd(camera_set_key, {f"{frame_hash}:{context_str}": time.time()})
                cache.expire(camera_set_key, 60)
                cache.incr("cache:stats:misses")
            except Exception as e:
                logger.warning("VERIFY call failed: %s", e)
                det["verified"] = False
                det["verification_error"] = str(e)
```

Add import for `time` at top.

- [ ] **Step 3: Run ALL existing tests to check no regression**

```bash
$env:AIMPLATFORM_ENV='test'; $env:LOG_LEVEL='ERROR'; uv run pytest --ignore=models/test_inference.py -v
```

- [ ] **Step 4: Commit**

```bash
git add src/pipeline/verify_handler.py
git commit -m "feat: verify handler cache integration (sync Redis)"
```

---

### Task 5: Agent Path Cache Integration (Async)

**Files:**
- Modify: `src/agent/agent.py`
- Test: `tests/test_agent_cache.py`

- [ ] **Step 1: Write test `tests/test_agent_cache.py`**

```python
import pytest
from unittest.mock import AsyncMock, patch
from src.agent.agent import CVAgent


@pytest.mark.asyncio
async def test_analyze_checks_cache_before_llm() -> None:
    mock_llm = AsyncMock()
    mock_tools = AsyncMock()
    mock_tools.get_openai_specs.return_value = []
    mock_cache = AsyncMock()
    mock_cache.get.return_value = None  # miss → proceed to LLM

    agent = CVAgent(mock_llm, mock_tools)
    agent._cache = mock_cache

    with patch.object(agent.llm, "chat_with_image", return_value={"content": '{"scene_type": "indoor"}'}):
        result = await agent.analyze(
            {"camera_id": "cam-1"},
            image_data=b"fake_frame_bytes",
        )
    assert mock_cache.get.called
    assert mock_cache.set.called  # stored after LLM call


@pytest.mark.asyncio
async def test_analyze_returns_cached_result() -> None:
    mock_llm = AsyncMock()
    mock_tools = AsyncMock()
    mock_tools.get_openai_specs.return_value = []
    mock_cache = AsyncMock()
    from src.cache.result_cache import CacheResult
    mock_cache.get.return_value = CacheResult(
        result={"path": "agent", "analysis": {"scene_type": "indoor"}, "latency_ms": 10, "tool_results": {}},
        created_at=100.0,
        context_hash="",
    )

    agent = CVAgent(mock_llm, mock_tools)
    agent._cache = mock_cache

    result = await agent.analyze(
        {"camera_id": "cam-1"},
        image_data=b"fake_frame_bytes",
    )
    assert result["analysis"]["scene_type"] == "indoor"
    mock_llm.chat_with_image.assert_not_called()
```

- [ ] **Step 2: Run to verify failure**

```bash
$env:AIMPLATFORM_ENV='test'; $env:LOG_LEVEL='ERROR'; uv run pytest tests/test_agent_cache.py -v --ignore=models/test_inference.py
```

Expected: assertion errors

- [ ] **Step 3: Modify `CVAgent` in `src/agent/agent.py`**

Add cache integration:

```python
import json
import logging
import time
import re
import hashlib
from typing import Any

from src.agent.client import LLMClient
from src.agent.tools import ToolRegistry

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "你是一个计算机视觉分析助手。分析图像内容并输出结构化 JSON。\n\n"
    "任务：\n"
    "1. 描述场景类型（室内/室外/交通/安防/其他）\n"
    "2. 列出检测到的目标及其属性\n"
    "3. 识别异常情况（如有）\n\n"
    "输出格式：\n"
    "{\n"
    '    "scene_type": "string",\n'
    '    "objects": [{"label": "string", "count": int, "details": "string"}],\n'
    '    "anomalies": [{"type": "string", "description": "string", "confidence": float}],\n'
    '    "summary": "string"\n'
    "}\n\n"
    "如果图像无法分析，返回 {\"error\": \"无法分析图像\", \"reason\": \"...\"}。"
)
```

At end of file, modify `analyze()`:

```python
    async def analyze(
        self,
        scene_context: dict[str, Any],
        image_data: bytes | None = None,
    ) -> dict[str, Any]:
        camera_id = scene_context.get("camera_id", "")
        system_prompt = SYSTEM_PROMPT
        context_hash = hashlib.sha256(system_prompt.encode()).hexdigest()[:16]
        frame_hash = ""

        if image_data:
            from src.cache.frame_hasher import FrameHasher
            hasher = FrameHasher()
            frame_hash = hasher.compute(image_data)

            cache = await self._get_cache()
            if cache:
                cached = await cache.get(camera_id, frame_hash, context_hash)
                if cached:
                    return cached.result

        start = time.monotonic()
        tool_specs = self.tools.get_openai_specs()
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(scene_context, ensure_ascii=False)},
        ]

        if image_data:
            response = await self.llm.chat_with_image(
                prompt=json.dumps(scene_context, ensure_ascii=False),
                image_data=image_data,
                tools=tool_specs if tool_specs else None,
            )
        else:
            response = await self.llm.chat(
                messages=messages,
                tools=tool_specs if tool_specs else None,
            )
        # ... rest unchanged ...

        if cache and image_data and frame_hash:
            await cache.set(camera_id, frame_hash, result, context_hash)

        return result
```

Add `_get_cache` method:

```python
    async def _get_cache(self):
        if not hasattr(self, "_cache") or self._cache is None:
            try:
                from src.cache.result_cache import ResultCache
                from src.core.redis_client import get_redis
                redis = await get_redis()
                self._cache = ResultCache(redis)
            except Exception as e:
                logger.warning("cache unavailable: %s", e)
                self._cache = None
        return self._cache
```

- [ ] **Step 4: Run tests**

```bash
$env:AIMPLATFORM_ENV='test'; $env:LOG_LEVEL='ERROR'; uv run pytest tests/test_agent_cache.py -v --ignore=models/test_inference.py
```

Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add src/agent/agent.py tests/test_agent_cache.py
git commit -m "feat: Agent path cache integration (async ResultCache)"
```

---

### Task 6: Config + Startup + Final Verification

**Files:**
- Modify: `config/default.yaml`
- Modify: `src/api/app.py`

- [ ] **Step 1: Add `result_cache` config to `config/default.yaml`**

Insert before the `llm:` section:

```yaml
result_cache:
  enabled: true
  ttl_seconds: 60
  hash_threshold: 8
  max_candidates: 20
```

- [ ] **Step 2: Register Redis startup/shutdown in `src/api/app.py`**

Find the existing startup event handler. Add Redis init:

```python
from src.core.redis_client import get_redis, close_redis

# In the existing startup handler:
    try:
        await get_redis()
        logger.info("Redis connection established")
    except Exception as e:
        logger.warning("Redis unavailable: %s", e)

# In the existing shutdown handler:
    await close_redis()
```

- [ ] **Step 3: Run full test suite**

```bash
$env:AIMPLATFORM_ENV='test'; $env:LOG_LEVEL='ERROR'; uv run pytest --ignore=models/test_inference.py -v --tb=short 2>&1
```

Expected: all tests pass (check no regression)

- [ ] **Step 4: Commit**

```bash
git add config/default.yaml src/api/app.py
git commit -m "chore: result_cache config + Redis lifecycle in app"
```

---

### Self-Review Checklist

1. **Spec coverage**: Every section in the spec has a corresponding task:
   - FrameHasher → Task 2
   - ResultCache (async) → Task 3
   - Redis key schema → Tasks 3, 4 (shared schema)
   - VERIFY integration → Task 4
   - Agent path integration → Task 5
   - Config → Task 6
   - Stats monitoring → Task 3 (get_stats)

2. **Placeholder scan**: All steps have complete code, no "TBD" or "implement later"

3. **Type consistency**: 
   - `FrameHasher.compute()` returns `str` (16 hex chars) — consistent across all tasks
   - `ResultCache.get()` returns `CacheResult | None` — consistent
   - Redis key pattern `cache:result:{camera_id}:{hash_hex}` — same in Tasks 3, 4
