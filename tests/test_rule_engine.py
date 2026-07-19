from src.pipeline.rule_engine import CameraRuleState, Detection, RuleEngine, RuleEvaluationResult


def test_detection_defaults() -> None:
    d = Detection(bbox=(0.1, 0.2, 0.3, 0.4), confidence=0.95, label="person")
    assert d.track_id is None


def test_detection_with_track_id() -> None:
    d = Detection(bbox=(0.1, 0.2, 0.3, 0.4), confidence=0.95, label="person", track_id="trk_001")
    assert d.track_id == "trk_001"


def test_rule_evaluation_result_fields() -> None:
    r = RuleEvaluationResult(
        triggered=True, rule_id=1, binding_id=1, camera_id="cam-1",
        rule_type="region_intrusion",
        matches=[{"track_id": "trk_001", "action": "enter"}],
        details={"polygon": [[0,0],[1,0],[1,1],[0,1]]},
    )
    assert r.triggered is True


def test_camera_rule_state_get_or_create() -> None:
    state = CameraRuleState()
    tracks = state.get_or_create("cam-1", 1)
    assert isinstance(tracks, dict)
    assert len(tracks) == 0


def test_camera_rule_state_track_object() -> None:
    state = CameraRuleState()
    tracks = state.get_or_create("cam-1", 1)
    tracks["trk_001"] = CameraRuleState.TrackedObject(
        track_id="trk_001", enter_time=100.0, last_seen=100.0, positions=[(0.5, 0.5)],
    )
    assert state.get_or_create("cam-1", 1)["trk_001"].track_id == "trk_001"


def test_camera_rule_state_separate_cameras() -> None:
    state = CameraRuleState()
    t1 = state.get_or_create("cam-1", 1)
    t2 = state.get_or_create("cam-2", 1)
    t1["trk_001"] = CameraRuleState.TrackedObject("trk_001", 0, 0, [(0, 0)])
    assert "trk_001" not in t2


def test_camera_rule_state_cleanup_removes_old() -> None:
    import time
    state = CameraRuleState()
    tracks = state.get_or_create("cam-1", 1)
    tracks["old"] = CameraRuleState.TrackedObject("old", 0, 0, [(0, 0)])
    tracks["fresh"] = CameraRuleState.TrackedObject("fresh", time.time(), time.time(), [(0, 0)])
    state.cleanup(max_age_seconds=30)
    assert "old" not in state.get_or_create("cam-1", 1)
    assert "fresh" in state.get_or_create("cam-1", 1)


def test_point_in_polygon_inside() -> None:
    engine = RuleEngine()
    polygon = [[0, 0], [10, 0], [10, 10], [0, 10]]
    assert engine.point_in_polygon((5, 5), polygon) is True


def test_point_in_polygon_outside() -> None:
    engine = RuleEngine()
    polygon = [[0, 0], [10, 0], [10, 10], [0, 10]]
    assert engine.point_in_polygon((15, 15), polygon) is False


def test_region_intrusion_enter_triggers() -> None:
    engine = RuleEngine()
    state = CameraRuleState()
    rule = type("MockRule", (), {"id": 1, "rule_type": "region_intrusion",
        "config": '{"polygon": [[0,0],[10,0],[10,10],[0,10]], "alert_on": "enter"}'})()
    binding = type("MockBinding", (), {"id": 1, "rule_id": 1, "camera_id": "cam-1", "config_overrides": None})()
    detections = [Detection(bbox=(4, 4, 6, 6), confidence=0.9, label="person", track_id="trk_001")]
    result = engine.evaluate(rule, binding, "cam-1", detections, state)
    assert result is not None
    assert result.triggered is True
    assert result.rule_type == "region_intrusion"


def test_region_intrusion_no_repeat_trigger() -> None:
    engine = RuleEngine()
    state = CameraRuleState()
    rule = type("MockRule", (), {"id": 1, "rule_type": "region_intrusion",
        "config": '{"polygon": [[0,0],[10,0],[10,10],[0,10]], "alert_on": "enter"}'})()
    binding = type("MockBinding", (), {"id": 1, "rule_id": 1, "camera_id": "cam-1", "config_overrides": None})()
    detections = [Detection(bbox=(4, 4, 6, 6), confidence=0.9, label="person", track_id="trk_001")]
    engine.evaluate(rule, binding, "cam-1", detections, state)  # first trigger
    result = engine.evaluate(rule, binding, "cam-1", detections, state)  # same frame, still inside
    assert result is None


def test_count_threshold_above_triggers() -> None:
    engine = RuleEngine()
    state = CameraRuleState()
    rule = type("MockRule", (), {"id": 2, "rule_type": "count_threshold",
        "config": '{"min": 0, "max": 2, "direction": "above"}'})()
    binding = type("MockBinding", (), {"id": 2, "rule_id": 2, "camera_id": "cam-1", "config_overrides": None})()
    detections = [Detection(bbox=(0, 0, 1, 1), confidence=0.9, label="person") for _ in range(5)]
    result = engine.evaluate(rule, binding, "cam-1", detections, state)
    assert result is not None
    assert result.triggered is True
    assert result.details["count"] == 5
    assert result.details["threshold_max"] == 2


def test_count_threshold_below_triggers() -> None:
    engine = RuleEngine()
    state = CameraRuleState()
    rule = type("MockRule", (), {"id": 3, "rule_type": "count_threshold",
        "config": '{"min": 3, "max": 100, "direction": "below"}'})()
    binding = type("MockBinding", (), {"id": 3, "rule_id": 3, "camera_id": "cam-1", "config_overrides": None})()
    detections = [Detection(bbox=(0, 0, 1, 1), confidence=0.9, label="person") for _ in range(1)]
    result = engine.evaluate(rule, binding, "cam-1", detections, state)
    assert result is not None
    assert result.triggered is True
    assert result.details["count"] == 1


def test_count_threshold_no_trigger() -> None:
    engine = RuleEngine()
    state = CameraRuleState()
    rule = type("MockRule", (), {"id": 4, "rule_type": "count_threshold",
        "config": '{"min": 0, "max": 5, "direction": "within"}'})()
    binding = type("MockBinding", (), {"id": 4, "rule_id": 4, "camera_id": "cam-1", "config_overrides": None})()
    detections = [Detection(bbox=(0, 0, 1, 1), confidence=0.9, label="person") for _ in range(3)]
    result = engine.evaluate(rule, binding, "cam-1", detections, state)
    assert result is None
