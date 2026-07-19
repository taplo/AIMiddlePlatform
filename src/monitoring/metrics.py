import time
from collections.abc import Callable

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


class StatsRingBuffer:
    def __init__(self, maxlen: int = 300) -> None:
        self.maxlen = maxlen
        self._timestamps: list[float] = []
        self._qps: list[float] = []
        self._p50: list[float] = []
        self._p95: list[float] = []
        self._p99: list[float] = []
        self._err_rate: list[float] = []

    def push(self, qps: float, p50: float, p95: float, p99: float, err_rate: float) -> None:
        self._timestamps.append(time.time())
        self._qps.append(qps)
        self._p50.append(p50)
        self._p95.append(p95)
        self._p99.append(p99)
        self._err_rate.append(err_rate)
        if len(self._timestamps) > self.maxlen:
            self._timestamps.pop(0)
            self._qps.pop(0)
            self._p50.pop(0)
            self._p95.pop(0)
            self._p99.pop(0)
            self._err_rate.pop(0)

    def to_dict(self) -> dict:
        return {
            "timestamps": [f"{t:.3f}" for t in self._timestamps],
            "qps": self._qps[:],
            "p50": self._p50[:],
            "p95": self._p95[:],
            "p99": self._p99[:],
            "error_rate": self._err_rate[:],
        }


_stats_buffer = StatsRingBuffer()


def get_stats_buffer() -> StatsRingBuffer:
    return _stats_buffer
