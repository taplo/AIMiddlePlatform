import time
from collections import deque
from dataclasses import dataclass

import numpy as np


@dataclass
class CachedFrame:
    data: np.ndarray
    timestamp: float


class VideoRingBuffer:
    def __init__(self, default_duration: float = 5.0) -> None:
        self.default_duration = default_duration
        self._buffers: dict[str, deque[CachedFrame]] = {}
        self._durations: dict[str, float] = {}

    def set_duration(self, camera_id: str, duration: float) -> None:
        duration = max(1.0, min(duration, 60.0))
        self._durations[camera_id] = duration

    def _get_duration(self, camera_id: str) -> float:
        return self._durations.get(camera_id, self.default_duration)

    def push(self, camera_id: str, frame: np.ndarray) -> None:
        if camera_id not in self._buffers:
            self._buffers[camera_id] = deque()
        now = time.time()
        buf = self._buffers[camera_id]
        buf.append(CachedFrame(data=frame, timestamp=now))
        cutoff = now - self._get_duration(camera_id)
        while buf and buf[0].timestamp < cutoff:
            buf.popleft()

    def get_segment(self, camera_id: str, start: float, end: float) -> list[CachedFrame]:
        buf = self._buffers.get(camera_id)
        if not buf:
            return []
        return [f for f in buf if start <= f.timestamp <= end]

    def get_recent(self, camera_id: str, count: int = 5) -> list[CachedFrame]:
        buf = self._buffers.get(camera_id)
        if not buf:
            return []
        return list(buf)[-count:]

    def clear(self, camera_id: str) -> None:
        self._buffers.pop(camera_id, None)

    def stats(self, camera_id: str) -> dict:
        buf = self._buffers.get(camera_id)
        return {
            "camera_id": camera_id,
            "duration": self._get_duration(camera_id),
            "buffered_frames": len(buf) if buf else 0,
        }
