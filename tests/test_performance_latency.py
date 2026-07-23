import time

import pytest
from fastapi.testclient import TestClient

from src.api.app import app
from src.core.security import get_api_key_store

client = TestClient(app)
_API_KEY = "sk-bench-key-0000000000000000000000001"


@pytest.fixture(autouse=True, scope="module")
def _setup():
    store = get_api_key_store()
    store.add_key("bench", _API_KEY, rate_per_second=10000)


def _bench(endpoint: str, n: int = 100) -> dict:
    times = []
    for _ in range(n):
        t0 = time.monotonic()
        resp = client.get(endpoint, headers={"X-API-Key": _API_KEY})
        resp.raise_for_status()
        times.append(time.monotonic() - t0)

    times.sort()
    total = len(times)
    return {
        "endpoint": endpoint,
        "n": n,
        "min": min(times),
        "max": max(times),
        "p50": times[int(total * 0.50)],
        "p95": times[int(total * 0.95)],
        "p99": times[int(total * 0.99)],
        "mean": sum(times) / total,
    }


def test_fast_path_ping_latency():
    result = _bench("/api/v1/analyze/ping", n=100)
    print(f"\nPing latency: p50={result['p50']*1000:.1f}ms p95={result['p95']*1000:.1f}ms p99={result['p99']*1000:.1f}ms")
    assert result["p95"] < 0.3, f"p95 ping latency {result['p95']*1000:.1f}ms exceeds 300ms"
    assert result["mean"] < 0.1, f"mean ping latency {result['mean']*1000:.1f}ms exceeds 100ms"


def test_fast_path_health_latency():
    result = _bench("/api/v1/health", n=100)
    print(f"\nHealth latency: p50={result['p50']*1000:.1f}ms p95={result['p95']*1000:.1f}ms p99={result['p99']*1000:.1f}ms")
    assert result["p95"] < 0.3, f"p95 health latency {result['p95']*1000:.1f}ms exceeds 300ms"


def test_fast_path_ping_p99_strict():
    result = _bench("/api/v1/analyze/ping", n=200)
    assert result["p99"] < 0.5, f"p99 ping latency {result['p99']*1000:.1f}ms exceeds 500ms"
