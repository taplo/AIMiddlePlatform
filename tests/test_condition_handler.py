import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch
from src.pipeline.condition_handler import condition_handler, init_session_factory


@pytest.fixture(autouse=True)
def _ensure_session_factory():
    """Ensure _session_factory is set so condition_handler doesn't short-circuit."""
    init_session_factory(MagicMock(return_value=MagicMock()))
    yield


@pytest.mark.asyncio
async def test_condition_no_rules() -> None:
    result = await condition_handler({"camera_id": "cam-1"}, {}, {})
    assert result["condition_results"] == []
    assert result["triggered"] is False


@pytest.mark.asyncio
async def test_condition_with_rule_trigger() -> None:
    mock_result = MagicMock()
    mock_result.triggered = True
    mock_result.rule_id = 1
    mock_result.binding_id = 1
    mock_result.camera_id = "cam-1"
    mock_result.rule_type = "region_intrusion"
    mock_result.matches = [{"track_id": "trk_001", "action": "enter"}]
    mock_result.details = {"polygon": [[0, 0], [10, 0], [10, 10], [0, 10]]}

    mock_db = AsyncMock()
    mock_binding = MagicMock(rule_id=1, camera_id="cam-1", scene_type=None, id=1, config_overrides=None)
    mock_db.execute.return_value = MagicMock()
    mock_db.execute.return_value.scalars.return_value.all.return_value = [mock_binding]
    mock_rule = MagicMock()
    mock_rule.id = 1
    mock_rule.rule_type = "region_intrusion"
    mock_rule.config = json.dumps({"polygon": [[0, 0], [10, 0], [10, 10], [0, 10]], "alert_on": "enter"})
    mock_rule.severity = "high"
    mock_rule.name = "test rule"
    mock_db.get.return_value = mock_rule

    mock_db.__aenter__.return_value = mock_db
    mock_factory = MagicMock(return_value=mock_db)
    init_session_factory(mock_factory)

    with patch("src.pipeline.condition_handler.RuleEngine") as MockEngine, \
         patch("src.pipeline.condition_handler.CameraRuleState") as MockState:
        MockEngine.return_value.evaluate.return_value = mock_result

        result = await condition_handler({"camera_id": "cam-1", "scene_type": "", "task_id": "t1"}, {"all_detections": []}, {"rule_refs": [1]})
        assert result["triggered"] is True
        assert len(result["condition_results"]) == 1
        mock_db.add.assert_called_once()
