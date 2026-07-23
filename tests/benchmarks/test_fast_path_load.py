import os
import time
from unittest.mock import patch

import fakeredis
import numpy as np
import pytest


_FAKE_KEY = "bench:sk-load-test-key-00001:100"


@pytest.fixture(scope="module", autouse=True)
def _setup_env():
    existing = os.environ.get("API_KEYS", "")
    os.environ["API_KEYS"] = f"{existing};{_FAKE_KEY}" if existing else _FAKE_KEY
    yield
    os.environ["API_KEYS"] = existing


class _FakeRedis:
    def __init__(self):
        self._inner = fakeredis.FakeAsyncRedis()

    async def close(self):
        pass

    async def ping(self):
        return True

    def __getattr__(self, name):
        return getattr(self._inner, name)


@pytest.fixture(scope="module")
def _fake_redis():
    return _FakeRedis()


@pytest.fixture(scope="module")
def client(_fake_redis):
    from src.api.app import app
    from fastapi.testclient import TestClient

    patches = [
        patch("src.queue.redis_streams.get_redis", return_value=_fake_redis),
        patch("src.core.redis_client.get_redis", return_value=_fake_redis),
    ]
    for p in patches:
        p.start()
    with TestClient(app) as c:
        yield c
    for p in patches:
        p.stop()


def _synthetic_frame(width=640, height=480) -> bytes:
    import cv2
    img = np.random.randint(0, 255, (height, width, 3), dtype=np.uint8)
    cv2.rectangle(img, (100, 100), (300, 300), (0, 255, 0), 2)
    cv2.circle(img, (400, 200), 50, (0, 0, 255), 2)
    _, buf = cv2.imencode(".jpg", img)
    return buf.tobytes()


@pytest.mark.benchmark
def test_fast_path_concurrent_load(client):
    num_cameras = int(os.environ.get("LOAD_NUM_CAMERAS", "20"))
    requests_per_camera = int(os.environ.get("LOAD_REQUESTS_PER_CAMERA", "5"))
    total_requests = num_cameras * requests_per_camera
    api_key = _FAKE_KEY.split(":")[1]

    frame_bytes = _synthetic_frame()
    import base64
    frame_b64 = base64.b64encode(frame_bytes).decode()
    headers = {"X-API-Key": api_key}
    latencies = []
    errors = []

    for cam_idx in range(num_cameras):
        camera_id = f"load-cam-{cam_idx:04d}"
        for req_idx in range(requests_per_camera):
            start = time.monotonic()
            resp = client.post(
                "/api/v1/analyze/frame",
                json={
                    "frame": frame_b64,
                    "camera_id": camera_id,
                    "scene_type": "parking_lot",
                },
                headers=headers,
            )
            elapsed = (time.monotonic() - start) * 1000
            latencies.append(elapsed)
            if resp.status_code != 200:
                errors.append({"camera": camera_id, "status": resp.status_code, "body": resp.text[:100]})

    latencies.sort()
    p50 = latencies[len(latencies) // 2]
    p95 = latencies[int(len(latencies) * 0.95)]
    p99 = latencies[int(len(latencies) * 0.99)]
    avg = sum(latencies) / len(latencies)
    throughput = total_requests / (sum(latencies) / 1000) if latencies else 0

    print(f"\n  Cameras: {num_cameras}, Requests/camera: {requests_per_camera}")
    print(f"  Total requests: {total_requests}, Errors: {len(errors)}")
    print(f"  p50: {p50:.1f}ms, p95: {p95:.1f}ms, p99: {p99:.1f}ms")
    print(f"  Avg: {avg:.1f}ms, Throughput: {throughput:.0f} req/s")

    assert len(errors) == 0, f"{len(errors)} requests failed: {errors[:3]}"
    assert p95 < 500, f"p95 latency {p95:.1f}ms exceeds 500ms limit"


@pytest.mark.benchmark
def test_fast_path_health_under_load(client):
    num_checks = int(os.environ.get("LOAD_HEALTH_CHECKS", "10"))
    api_key = _FAKE_KEY.split(":")[1]
    headers = {"X-API-Key": api_key}
    latencies = []

    for _ in range(num_checks):
        start = time.monotonic()
        client.get("/api/v1/health", headers=headers)
        elapsed = (time.monotonic() - start) * 1000
        latencies.append(elapsed)

    latencies.sort()
    p50 = latencies[len(latencies) // 2]
    p95 = latencies[int(len(latencies) * 0.95)]

    print(f"\n  Health checks: {num_checks}")
    print(f"  p50: {p50:.1f}ms, p95: {p95:.1f}ms")

    assert p95 < 300, f"Health check p95 {p95:.1f}ms exceeds 300ms limit"
