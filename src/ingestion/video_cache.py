import logging
import sys
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

import cv2
import numpy as np

logger = logging.getLogger(__name__)

_MAX_MEMORY_BYTES = 500 * 1024 * 1024
_DEFAULT_DURATION = 30.0
_MIN_DURATION = 1.0
_MAX_DURATION = 300.0


@dataclass
class CachedFrame:
    data: bytes
    timestamp: float
    task_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    _decoded: np.ndarray | None = field(default=None, repr=False)

    def memory_bytes(self) -> int:
        return sys.getsizeof(self.data) + sys.getsizeof(self.metadata)

    def decode(self) -> np.ndarray:
        if self._decoded is not None:
            return self._decoded
        arr = np.frombuffer(self.data, dtype=np.uint8)
        self._decoded = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        return self._decoded


class VideoRingBuffer:
    def __init__(self, default_duration: float = _DEFAULT_DURATION, max_memory: int = _MAX_MEMORY_BYTES) -> None:
        self.default_duration = default_duration
        self.max_memory = max_memory
        self._buffers: dict[str, deque[CachedFrame]] = {}
        self._durations: dict[str, float] = {}

    def set_duration(self, camera_id: str, duration: float) -> None:
        clamped = max(_MIN_DURATION, min(duration, _MAX_DURATION))
        self._durations[camera_id] = clamped

    def _get_duration(self, camera_id: str) -> float:
        return self._durations.get(camera_id, self.default_duration)

    def push(self, camera_id: str, frame: np.ndarray, task_id: str = "", metadata: dict | None = None) -> None:
        if camera_id not in self._buffers:
            self._buffers[camera_id] = deque()
        now = time.time()
        _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        cf = CachedFrame(data=buf.tobytes(), timestamp=now, task_id=task_id, metadata=metadata or {})
        self._buffers[camera_id].append(cf)
        self._trim(camera_id)
        self._enforce_memory_limit()

    def _trim(self, camera_id: str) -> None:
        buf = self._buffers.get(camera_id)
        if not buf:
            return
        cutoff = time.time() - self._get_duration(camera_id)
        while buf and buf[0].timestamp < cutoff:
            buf.popleft()

    def _enforce_memory_limit(self) -> None:
        total = sum(cf.memory_bytes() for buf in self._buffers.values() for cf in buf)
        if total <= self.max_memory:
            return
        ordered: list[tuple[float, str, CachedFrame]] = []
        for cid, buf in self._buffers.items():
            for cf in buf:
                ordered.append((cf.timestamp, cid, cf))
        ordered.sort(key=lambda x: x[0])
        freed = 0
        for ts, cid, cf in ordered:
            if total - freed <= self.max_memory:
                break
            self._buffers[cid].remove(cf)
            freed += cf.memory_bytes()
            if not self._buffers[cid]:
                del self._buffers[cid]
        logger.info("Video cache evicted %d bytes to stay under memory limit", freed)

    def get_segment(self, camera_id: str, start: float, end: float) -> list[CachedFrame]:
        buf = self._buffers.get(camera_id)
        if not buf:
            return []
        return [f for f in buf if start <= f.timestamp <= end]

    def get_segment_around(self, camera_id: str, timestamp: float, window_seconds: float = 2.0) -> list[CachedFrame]:
        return self.get_segment(camera_id, timestamp - window_seconds, timestamp + window_seconds)

    def get_recent(self, camera_id: str, count: int = 5) -> list[CachedFrame]:
        buf = self._buffers.get(camera_id)
        if not buf:
            return []
        return list(buf)[-count:]

    def clear(self, camera_id: str) -> None:
        self._buffers.pop(camera_id, None)

    def stats(self, camera_id: str) -> dict:
        buf = self._buffers.get(camera_id)
        frames = list(buf) if buf else []
        return {
            "camera_id": camera_id,
            "duration": self._get_duration(camera_id),
            "buffered_frames": len(frames),
            "memory_bytes": sum(f.memory_bytes() for f in frames),
            "oldest_timestamp": frames[0].timestamp if frames else None,
            "newest_timestamp": frames[-1].timestamp if frames else None,
        }

    def all_stats(self) -> dict[str, dict]:
        return {cid: self.stats(cid) for cid in list(self._buffers.keys())}

    def estimate_total_memory(self) -> int:
        return sum(cf.memory_bytes() for buf in self._buffers.values() for cf in buf)


_cache_instance: VideoRingBuffer | None = None


def get_cache() -> VideoRingBuffer:
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = VideoRingBuffer()
    return _cache_instance


def init_cache(default_duration: float = _DEFAULT_DURATION, max_memory: int = _MAX_MEMORY_BYTES) -> VideoRingBuffer:
    global _cache_instance
    _cache_instance = VideoRingBuffer(default_duration=default_duration, max_memory=max_memory)
    logger.info("Video cache initialized: duration=%ss, max_memory=%dMB", default_duration, max_memory // (1024 * 1024))
    return _cache_instance
