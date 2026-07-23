"""E2E tests with fakeredis — verify the full API flow without real Redis."""

import base64
import os
from pathlib import Path
from unittest.mock import patch

import cv2
import fakeredis
import numpy as np
import pytest
from fastapi.testclient import TestClient

from src.api.app import app

_TEST_IMAGE = Path(__file__).resolve().parent.parent / "bus_test.jpg"
_API_KEY = "sk-redis-e2e-key-00000000"


@pytest.fixture(scope="module", autouse=True)
def _setup_env():
    key = os.environ.get("API_KEYS", "")
    api_keys = f"{key};e2e:{_API_KEY}:100" if key else f"e2e:{_API_KEY}:100"
    os.environ["API_KEYS"] = api_keys


class _FakeRedis:
    """Wraps fakeredis.FakeAsyncRedis to match RedisStreamQueue expectations."""

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
    with patch("src.queue.redis_streams.get_redis", return_value=_fake_redis):
        with patch("src.core.redis_client.get_redis", return_value=_fake_redis):
            with TestClient(app) as c:
                yield c


@pytest.fixture(scope="module")
def test_image():
    img = cv2.imread(str(_TEST_IMAGE))
    assert img is not None, f"Test image not found: {_TEST_IMAGE}"
    return img


@pytest.fixture
def headers():
    return {"X-API-Key": _API_KEY}


def _encode_image(img: np.ndarray) -> str:
    _, buf = cv2.imencode(".jpg", img)
    return base64.b64encode(buf).decode()


def test_ping_with_fake_redis(client, headers):
    resp = client.get("/api/v1/analyze/ping", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


def test_ping_without_api_key(client):
    resp = client.get("/api/v1/analyze/ping")
    assert resp.status_code == 200


def test_submit_frame_via_api(client, headers, test_image):

    frame_b64 = _encode_image(test_image)
    resp = client.post(
        "/api/v1/analyze/frame",
        json={"frame": frame_b64, "camera_id": "e2e-cam-01", "scene_type": "parking_lot"},
        headers=headers,
    )
    data = resp.json()
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {data}"
    assert "task_id" in data, f"Missing task_id: {data}"
    assert data["status"] in ("queued", "rejected", "skipped"), f"Unexpected status: {data}"


def test_submit_frame_no_scene_type(client, headers, test_image):
    frame_b64 = _encode_image(test_image)
    resp = client.post(
        "/api/v1/analyze/frame",
        json={"frame": frame_b64, "camera_id": "e2e-cam-02"},
        headers=headers,
    )
    data = resp.json()
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {data}"
    assert "task_id" in data


def test_submit_frame_too_large(client, headers):
    big_frame = "A" * (10 * 1024 * 1024 + 1)
    resp = client.post(
        "/api/v1/analyze/frame",
        json={"frame": big_frame, "camera_id": "e2e-cam-03"},
        headers=headers,
    )
    assert resp.status_code == 413


def test_health_endpoint(client, headers):
    resp = client.get("/api/v1/health", headers=headers)
    assert resp.status_code == 200


def test_list_models(client, headers):
    resp = client.get("/api/v1/models/", headers=headers)
    assert resp.status_code == 200
    models = resp.json()
    assert isinstance(models, list)
