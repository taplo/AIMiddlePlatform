from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.ws.manager import ConnectionManager


def _ws():
    ws = MagicMock()
    ws.accept = AsyncMock()
    ws.send_text = AsyncMock()
    return ws


@pytest.mark.asyncio
async def test_connect_adds_ws():
    mgr = ConnectionManager("redis://localhost")
    ws = _ws()
    await mgr.connect(ws)
    assert ws in mgr._connections
    assert ws.accept.called


@pytest.mark.asyncio
async def test_disconnect_removes_ws():
    mgr = ConnectionManager("redis://localhost")
    ws = _ws()
    await mgr.connect(ws)
    await mgr.disconnect(ws)
    assert ws not in mgr._connections


@pytest.mark.asyncio
async def test_broadcast_sends_to_all():
    mgr = ConnectionManager("redis://localhost")
    ws1 = _ws()
    ws2 = _ws()
    await mgr.connect(ws1)
    await mgr.connect(ws2)
    await mgr._broadcast('{"type": "test"}')
    ws1.send_text.assert_called_once_with('{"type": "test"}')
    ws2.send_text.assert_called_once_with('{"type": "test"}')


@pytest.mark.asyncio
async def test_broadcast_removes_dead_connections():
    mgr = ConnectionManager("redis://localhost")
    ws1 = _ws()
    ws2 = _ws()
    ws1.send_text.side_effect = Exception("dead")
    await mgr.connect(ws1)
    await mgr.connect(ws2)
    await mgr._broadcast('{"type": "test"}')
    assert ws1 not in mgr._connections
    assert ws2 in mgr._connections


@pytest.mark.asyncio
async def test_start_and_stop():
    mgr = ConnectionManager("redis://localhost")
    mock_redis = AsyncMock()
    with patch.object(mgr, "_subscriber_loop", new_callable=AsyncMock):
        with patch("src.ws.manager.Redis.from_url", return_value=mock_redis):
            await mgr.start()
            assert mgr._subscriber_task is not None
            await mgr.stop()
            mock_redis.close.assert_awaited()
