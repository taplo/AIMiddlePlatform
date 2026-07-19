from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.worker import Worker


@pytest.mark.asyncio
async def test_save_result_publishes_analysis():
    worker = Worker.__new__(Worker)
    worker.db = MagicMock()

    with patch("src.worker.ws_publish", new_callable=AsyncMock) as mock_pub:
        with patch("src.worker.AsyncSession") as mock_session_cls:
            mock_session = AsyncMock()
            mock_session.add = MagicMock()
            mock_session_cls.return_value.__aenter__.return_value = mock_session
            mock_task = MagicMock()
            mock_task.task_id = "task-1"
            mock_task.camera_id = "cam-1"
            mock_task.status = "completed"
            mock_task.path_taken = "fast"
            mock_task.latency_ms = 123
            mock_task.result_json = '{"a": 1}'
            with patch("src.worker.Task", return_value=mock_task):
                with patch("src.worker.settings") as mock_settings:
                    mock_settings.get.return_value = True
                    await worker._save_result("task-1", "cam-1", {"path": "fast", "latency_ms": 123})
    mock_pub.assert_awaited_once()
    args, _ = mock_pub.call_args
    assert args[0] == "ws:analysis_result"
    assert args[1]["task_id"] == "task-1"
