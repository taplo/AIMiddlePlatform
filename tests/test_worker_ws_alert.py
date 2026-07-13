import pytest
from unittest.mock import patch, AsyncMock, MagicMock, ANY
from src.worker import _evaluate_rules_for_task


@pytest.mark.asyncio
async def test_evaluate_rules_publishes_alert():
    mock_rule = MagicMock()
    mock_rule.id = 1
    mock_rule.name = "test_rule"
    mock_rule.enabled = True
    mock_rule.rule_type = "count_threshold"
    mock_rule.config = '{"min":1,"direction":"below"}'
    mock_rule.severity = "high"

    mock_binding = MagicMock()
    mock_binding.id = 10
    mock_binding.camera_id = "cam-1"
    mock_binding.scene_type = None
    mock_binding.enabled = True
    mock_binding.rule_id = 1
    mock_binding.config_overrides = None

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mock_binding]
    mock_result.scalars.return_value.first.return_value = None

    with patch("src.worker.ws_publish", new_callable=AsyncMock) as mock_pub:
        with patch("src.worker.settings") as mock_settings:
            mock_settings.get.return_value = True
            with patch("src.worker.AsyncSession") as mock_session_cls:
                mock_session = AsyncMock()
                mock_session_cls.return_value.__aenter__.return_value = mock_session
                mock_session.execute = AsyncMock(return_value=mock_result)
                mock_session.get = AsyncMock(return_value=mock_rule)
                mock_session.add = MagicMock()
                mock_session.commit = AsyncMock()

                await _evaluate_rules_for_task(
                    MagicMock(), "task-1", "cam-1",
                    {"scene_type": "outdoor"}
                )
    mock_pub.assert_awaited()
