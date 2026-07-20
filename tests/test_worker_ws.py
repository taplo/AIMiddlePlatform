from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.worker import Worker


@pytest.mark.asyncio
async def test_save_result_publishes_analysis():
    import asyncio
    worker = Worker.__new__(Worker)
    worker.db = MagicMock()
    worker._db_queue = asyncio.Queue()
    worker._rule_queue = asyncio.Queue()

    with patch("src.worker.ws_publish", new_callable=AsyncMock) as mock_pub:
        with patch("src.worker.settings") as mock_settings:
            mock_settings.get.return_value = True
            await worker._enqueue_save("task-1", "cam-1", {"path": "fast", "latency_ms": 123})
    mock_pub.assert_awaited_once()
    args, _ = mock_pub.call_args
    assert args[0] == "ws:analysis_result"
    assert args[1]["task_id"] == "task-1"
