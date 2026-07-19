import logging

import cv2
import numpy as np

logger = logging.getLogger(__name__)


class AdaptiveFrameExtractor:
    def __init__(
        self,
        target_fps: float = 2.0,
        min_fps: float = 0.2,
        max_fps: float = 10.0,
        scene_change_threshold: float = 15.0,
        check_resolution: tuple[int, int] = (160, 90),
        backlog_size_fn=None,
    ) -> None:
        self.target_fps = target_fps
        self.min_fps = min_fps
        self.max_fps = max_fps
        self.scene_change_threshold = scene_change_threshold
        self.check_resolution = check_resolution
        self._backlog_size_fn = backlog_size_fn
        self._current_fps = target_fps
        self._prev_gray: np.ndarray | None = None
        self._frame_count = 0
        self._last_yield = 0.0

    @property
    def current_fps(self) -> float:
        return self._current_fps

    def _compute_scene_change(self, frame: np.ndarray) -> float:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        small = cv2.resize(gray, self.check_resolution, interpolation=cv2.INTER_LINEAR)
        if self._prev_gray is None:
            self._prev_gray = small
            return 0.0
        diff = cv2.absdiff(small, self._prev_gray).mean()
        self._prev_gray = small
        return diff

    def _adjust_fps(self, scene_change_score: float) -> None:
        backlog = self._backlog_size_fn() if self._backlog_size_fn else 0
        backpressure = max(0, backlog - 50) / 200.0
        backpressure = min(backpressure, 0.8)

        if scene_change_score > self.scene_change_threshold:
            target = self.target_fps * (1.0 - backpressure)
            self._current_fps = min(self._current_fps * 1.5, target, self.max_fps)
        else:
            decay = 0.95 - backpressure * 0.3
            self._current_fps = max(self._current_fps * decay, self.min_fps)

    def should_keep(self, frame: np.ndarray, now: float) -> bool:
        scene_score = self._compute_scene_change(frame)
        self._adjust_fps(scene_score)
        interval = 1.0 / self._current_fps if self._current_fps > 0 else 0
        if interval <= 0:
            self._last_yield = now
            return True
        if now - self._last_yield >= interval:
            self._last_yield = now
            return True
        return False

    def reset(self) -> None:
        self._prev_gray = None
        self._current_fps = self.target_fps
        self._frame_count = 0
        self._last_yield = 0.0
