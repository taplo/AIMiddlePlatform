import time

import numpy as np
import pytest

from src.ingestion.video_cache import VideoRingBuffer, init_cache, get_cache


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
    cache.set_duration("cam-1", 999.0)
    assert cache.stats("cam-1")["duration"] == 300.0

    cache.set_duration("cam-1", 0.1)
    assert cache.stats("cam-1")["duration"] == 1.0


def test_push_with_metadata() -> None:
    cache = VideoRingBuffer(default_duration=30.0)
    img = np.zeros((10, 10, 3), dtype=np.uint8)
    cache.push("cam-1", img, task_id="task-001", metadata={"detections": 3})
    recent = cache.get_recent("cam-1", count=1)
    assert len(recent) == 1
    assert recent[0].task_id == "task-001"
    assert recent[0].metadata["detections"] == 3


def test_get_segment_returns_matching_frames() -> None:
    cache = VideoRingBuffer(default_duration=30.0)
    img = np.zeros((10, 10, 3), dtype=np.uint8)
    cache.push("cam-1", img)
    t = time.time()
    frames = cache.get_segment("cam-1", t - 1, t + 1)
    assert len(frames) >= 1


def test_get_segment_around() -> None:
    cache = VideoRingBuffer(default_duration=30.0)
    img = np.zeros((10, 10, 3), dtype=np.uint8)
    cache.push("cam-1", img)
    t = time.time()
    frames = cache.get_segment_around("cam-1", t, window_seconds=1.0)
    assert len(frames) >= 1


def test_memory_limit_eviction() -> None:
    cache = VideoRingBuffer(default_duration=30.0, max_memory=1024)
    for i in range(100):
        cache.push("cam-1", np.zeros((30, 30, 3), dtype=np.uint8))
    assert cache.estimate_total_memory() <= 2048


def test_all_stats() -> None:
    cache = VideoRingBuffer(default_duration=5.0)
    img = np.zeros((10, 10, 3), dtype=np.uint8)
    cache.push("cam-a", img)
    cache.push("cam-b", img)
    stats = cache.all_stats()
    assert "cam-a" in stats
    assert "cam-b" in stats
    assert stats["cam-a"]["buffered_frames"] >= 1


def test_stats_returns_memory_bytes() -> None:
    cache = VideoRingBuffer(default_duration=5.0)
    img = np.zeros((10, 10, 3), dtype=np.uint8)
    cache.push("cam-1", img)
    s = cache.stats("cam-1")
    assert s["memory_bytes"] > 0
    assert s["oldest_timestamp"] is not None
    assert s["newest_timestamp"] is not None


def test_get_cache_singleton() -> None:
    c1 = get_cache()
    c2 = get_cache()
    assert c1 is c2


def test_init_cache_overrides_singleton() -> None:
    c = init_cache(default_duration=15.0, max_memory=256 * 1024 * 1024)
    assert c.default_duration == 15.0
    assert c.max_memory == 256 * 1024 * 1024
    assert get_cache() is c


def test_stats_for_missing_camera() -> None:
    cache = VideoRingBuffer()
    s = cache.stats("nonexistent")
    assert s["buffered_frames"] == 0
    assert s["memory_bytes"] == 0
