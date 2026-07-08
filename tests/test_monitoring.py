import pytest
from fastapi.testclient import TestClient

from src.monitoring.metrics import (
    request_total,
    dag_execution_total,
    dag_execution_latency,
    inference_total,
    path_decision_total,
    metrics_endpoint,
)
from src.monitoring.structured_log import JSONFormatter, log_with_fields
from src.monitoring.tracing import get_tracer


def test_metrics_endpoint_returns_valid_content() -> None:
    data = metrics_endpoint()
    assert isinstance(data, bytes)
    assert b"# HELP" in data or b"# TYPE" in data


def test_request_counter_increments() -> None:
    before = request_total.labels(method="GET", path="/test", status=200)._value.get()
    request_total.labels(method="GET", path="/test", status=200).inc()
    after = request_total.labels(method="GET", path="/test", status=200)._value.get()
    assert after == before + 1


def test_dag_metrics() -> None:
    dag_execution_total.labels(dag_name="test_dag", status="success").inc()
    dag_execution_latency.labels(dag_name="test_dag").observe(0.05)


def test_inference_metrics() -> None:
    inference_total.labels(model_id="test_model", status="success").inc()


def test_path_decision_metrics() -> None:
    path_decision_total.labels(path="fast", camera_id="cam-01").inc()


def test_json_formatter() -> None:
    import logging
    formatter = JSONFormatter()
    record = logging.LogRecord(
        name="test", level=logging.INFO, pathname="", lineno=0,
        msg="hello", args=(), exc_info=None,
    )
    output = formatter.format(record)
    import json
    parsed = json.loads(output)
    assert parsed["message"] == "hello"
    assert parsed["level"] == "INFO"


def test_log_with_fields() -> None:
    import logging
    logger = logging.getLogger("test_fields")
    logger.setLevel(logging.DEBUG)
    log_with_fields(logger, logging.INFO, "test message", extra_key="extra_value")


def test_tracer_available() -> None:
    tracer = get_tracer()
    assert tracer is not None


def test_metrics_route_via_api() -> None:
    from src.api.app import app
    client = TestClient(app)
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/plain")
