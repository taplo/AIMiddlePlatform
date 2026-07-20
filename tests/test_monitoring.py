import json
import logging

import pytest
from fastapi.testclient import TestClient

from src.monitoring.metrics import (
    dag_execution_latency,
    dag_execution_total,
    inference_total,
    metrics_endpoint,
    path_decision_total,
    request_total,
)
from src.monitoring.structured_log import JSONFormatter, log_with_fields
from src.monitoring.tracing import get_tracer, trace_async


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
    formatter = JSONFormatter()
    record = logging.LogRecord(
        name="test", level=logging.INFO, pathname="", lineno=0,
        msg="hello", args=(), exc_info=None,
    )
    output = formatter.format(record)
    parsed = json.loads(output)
    assert parsed["message"] == "hello"
    assert parsed["level"] == "INFO"


def test_log_with_fields() -> None:
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


def test_metrics_middleware_tracks_requests() -> None:
    from src.api.app import app
    client = TestClient(app)
    before = request_total.labels(method="GET", path="/api/v1/health", status=200)._value.get()
    client.get("/api/v1/health")
    after = request_total.labels(method="GET", path="/api/v1/health", status=200)._value.get()
    assert after == before + 1


def test_metrics_middleware_appears_in_prometheus_output() -> None:
    from src.api.app import app
    client = TestClient(app)
    client.get("/api/v1/health")
    data = metrics_endpoint()
    assert b"app_requests_total" in data


def test_json_logging_output(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO)
    logger = logging.getLogger("test_json_output")
    logger.info("json test message")
    assert len(caplog.records) >= 1


def test_log_with_fields_in_json_formatter() -> None:
    formatter = JSONFormatter()
    logger = logging.getLogger("test_fields_json")
    record = logger.makeRecord(
        logger.name, logging.INFO, "", 0, "field test", (), None,
    )
    record.extra_fields = {"method": "GET", "status": 200}
    output = formatter.format(record)
    parsed = json.loads(output)
    assert parsed["method"] == "GET"
    assert parsed["status"] == 200


def test_trace_async_decorator() -> None:
    calls = []

    @trace_async(span_name="test_span")
    async def traced_func(x: int) -> int:
        calls.append(x)
        return x * 2

    import asyncio
    result = asyncio.run(traced_func(21))
    assert result == 42
    assert calls == [21]


def test_worker_metrics_defined() -> None:
    from src.worker import worker_tasks_total, worker_tasks_latency
    assert worker_tasks_total is not None
    assert worker_tasks_latency is not None
    worker_tasks_total.labels(status="test").inc()
    worker_tasks_latency.observe(0.1)


def test_request_logger_excludes_metrics_path() -> None:
    from src.monitoring.request_logger import _EXCLUDE_PATHS
    assert "/metrics" in _EXCLUDE_PATHS
    assert "/api/v1/health" in _EXCLUDE_PATHS
