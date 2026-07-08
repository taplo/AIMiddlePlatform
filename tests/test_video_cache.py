import numpy as np

from src.ingestion.video_cache import VideoRingBuffer


def test_push_and_get_recent() -> None:
    cache = VideoRingBuffer(default_duration=5.0)
    for i in range(10):
        cache.push("cam-1", np.zeros((10, 10, 3), dtype=np.uint8))
    recent = cache.get_recent("cam-1", count=3)
    assert len(recent) == 3


def test_clear() -> None:
    cache = VideoRingBuffer(default_duration=5.0)
    cache.push("cam-1", np.zeros((10, 10, 3), dtype=np.uint8))
    cache.clear("cam-1")
    assert len(cache.get_recent("cam-1")) == 0


def test_per_camera_duration() -> None:
    cache = VideoRingBuffer(default_duration=5.0)
    cache.set_duration("cam-1", 30.0)
    stats = cache.stats("cam-1")
    assert stats["duration"] == 30.0

    cache.set_duration("cam-2", 60.0)
    stats = cache.stats("cam-2")
    assert stats["duration"] == 60.0


def test_duration_clamping() -> None:
    cache = VideoRingBuffer(default_duration=5.0)
    cache.set_duration("cam-1", 120.0)
    assert cache.stats("cam-1")["duration"] == 60.0

    cache.set_duration("cam-1", 0.1)
    assert cache.stats("cam-1")["duration"] == 1.0
