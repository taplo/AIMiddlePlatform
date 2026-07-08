import time
from collections.abc import Callable
from typing import Any

from prometheus_client import Counter, Gauge, Histogram, generate_latest

request_total = Counter(
    "app_requests_total",
    "Total HTTP requests",
    labelnames=["method", "path", "status"],
)

request_latency = Histogram(
    "app_request_latency_seconds",
    "HTTP request latency in seconds",
    labelnames=["method", "path"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)

dag_execution_total = Counter(
    "dag_execution_total",
    "Total DAG executions",
    labelnames=["dag_name", "status"],
)

dag_execution_latency = Histogram(
    "dag_execution_latency_seconds",
    "DAG execution latency in seconds",
    labelnames=["dag_name"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)

inference_total = Counter(
    "model_inference_total",
    "Total model inference calls",
    labelnames=["model_id", "status"],
)

inference_latency = Histogram(
    "model_inference_latency_seconds",
    "Model inference latency in seconds",
    labelnames=["model_id"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0),
)

path_decision_total = Counter(
    "path_decision_total",
    "Total path decisions",
    labelnames=["path", "camera_id"],
)

active_streams = Gauge("active_streams", "Currently active camera streams")

agent_analysis_total = Counter(
    "agent_analysis_total",
    "Total LLM agent analysis calls",
    labelnames=["status"],
)

agent_analysis_latency = Histogram(
    "agent_analysis_latency_seconds",
    "LLM agent analysis latency in seconds",
    buckets=(0.1, 0.5, 1.0, 2.5, 5.0, 10.0),
)


async def metrics_middleware(scope: dict, receive: Callable, send: Callable) -> None:
    if scope["type"] != "http":
        return
    path = scope.get("path", "unknown")
    method = scope.get("method", "GET")
    start = time.monotonic()
    status = [200]

    async def wrapped_send(message: dict) -> None:
        if message["type"] == "http.response.start":
            status[0] = message.get("status", 200)
        await send(message)

    try:
        await send  # passthrough
    finally:
        elapsed = time.monotonic() - start
        request_total.labels(method=method, path=path, status=status[0]).inc()
        request_latency.labels(method=method, path=path).observe(elapsed)


def metrics_endpoint() -> bytes:
    return generate_latest()
