import logging
import time
from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class SamplingResult:
    decision: str
    mse: float
    ssim: float | None


class AdaptiveFrameSampler:
    def __init__(
        self,
        mse_threshold_low: float = 0.5,
        mse_threshold_high: float = 3.0,
        ssim_threshold: float = 0.85,
        decay_seconds: float = 60.0,
    ):
        self.mse_low = mse_threshold_low
        self.mse_high = mse_threshold_high
        self.ssim_threshold = ssim_threshold
        self.decay = decay_seconds
        self._history: dict[str, tuple[float, np.ndarray]] = {}

    def _to_gray(self, image: np.ndarray) -> np.ndarray:
        return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image

    def _mse(self, a: np.ndarray, b: np.ndarray) -> float:
        return float(np.mean((a.astype(np.float32) - b.astype(np.float32)) ** 2))

    def _ssim(self, a: np.ndarray, b: np.ndarray) -> float:
        C1, C2 = (0.01 * 255) ** 2, (0.03 * 255) ** 2
        a_f, b_f = a.astype(np.float32), b.astype(np.float32)
        mu_a, mu_b = np.mean(a_f), np.mean(b_f)
        sigma_a2, sigma_b2 = np.var(a_f), np.var(b_f)
        sigma_ab = np.mean((a_f - mu_a) * (b_f - mu_b))
        return float((2 * mu_a * mu_b + C1) * (2 * sigma_ab + C2) / ((mu_a**2 + mu_b**2 + C1) * (sigma_a2 + sigma_b2 + C2)))

    def should_process(self, camera_id: str, image: np.ndarray, now: float | None = None) -> SamplingResult:
        now = now or time.time()
        gray = self._to_gray(image)
        medium = cv2.resize(gray, (128, 128), interpolation=cv2.INTER_AREA)
        tiny = cv2.resize(medium, (64, 64), interpolation=cv2.INTER_AREA)

        prev_entry = self._history.get(camera_id)
        if prev_entry is None or (now - prev_entry[0]) > self.decay:
            self._history[camera_id] = (now, medium)
            return SamplingResult(decision="process", mse=float("inf"), ssim=None)

        _, prev_medium = prev_entry
        prev_tiny = cv2.resize(prev_medium, (64, 64), interpolation=cv2.INTER_AREA)
        mse = self._mse(tiny, prev_tiny)

        if mse >= self.mse_high:
            self._history[camera_id] = (now, medium)
            return SamplingResult(decision="process", mse=mse, ssim=None)

        if mse < self.mse_low:
            return SamplingResult(decision="skip", mse=mse, ssim=None)

        ssim = self._ssim(medium, prev_medium)
        if ssim > self.ssim_threshold:
            return SamplingResult(decision="skip", mse=mse, ssim=ssim)

        self._history[camera_id] = (now, medium)
        return SamplingResult(decision="process", mse=mse, ssim=ssim)



