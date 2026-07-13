import pytest
from unittest.mock import AsyncMock, patch
from src.ws import publish


@pytest.mark.asyncio
async def test_publish_serializes_and_publishes():
    mock_redis = AsyncMock()
    async def mock_get() -> AsyncMock:
        return mock_redis
    with patch("src.ws.get_redis", new=mock_get):
        await publish("ws:test", {"key": "value"})
    mock_redis.publish.assert_awaited_once_with(
        "ws:test", '{"key": "value"}'
    )


@pytest.mark.asyncio
async def test_publish_fails_gracefully_on_redis_error():
    mock_redis = AsyncMock()
    mock_redis.publish.side_effect = ConnectionError("Redis down")
    async def mock_get() -> AsyncMock:
        return mock_redis
    with patch("src.ws.get_redis", new=mock_get):
        await publish("ws:test", {"key": "value"})
