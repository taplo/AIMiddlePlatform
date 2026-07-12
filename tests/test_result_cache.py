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
    mock_redis.get.return_value = json.dumps({
        "result": {"answer": 42},
        "created_at": time.time(),
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
    # First get returns None (exact miss), second returns hit data
    mock_redis.get.side_effect = [
        None,
        json.dumps({"result": {"answer": 42}, "created_at": time.time(), "context_hash": "ctx"}).encode(),
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
    mock_redis.get.return_value = None
    mock_redis.zrangebyscore.return_value = []
    cache = ResultCache(mock_redis)
    await cache.get("cam-1", "abcd" * 4)  # miss 1
    await cache.get("cam-2", "1234" * 4)  # miss 2
    mock_redis.get.side_effect = [b"0", b"2"]
    stats = await cache.get_stats()
    assert stats["hits"] == 0
    assert stats["misses"] == 2
    assert stats["total"] == 2
    assert stats["hit_rate"] == 0.0
