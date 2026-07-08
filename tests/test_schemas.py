from datetime import datetime

from src.core.schemas import AnalysisResult, ModelResult


def test_analysis_result_defaults() -> None:
    r = AnalysisResult(
        request_id="test-1",
        timestamp=datetime.now(),
        camera_id="cam-001",
    )
    assert r.results == []
    assert r.latency_ms == 0.0


def test_analysis_result_with_results() -> None:
    r = AnalysisResult(
        request_id="test-2",
        timestamp=datetime.now(),
        camera_id="cam-001",
        results=[
            ModelResult(model_id="detection", confidence=0.95, data={"count": 3}),
        ],
        latency_ms=150.0,
    )
    assert len(r.results) == 1
    assert r.results[0].model_id == "detection"
    assert r.results[0].confidence == 0.95
