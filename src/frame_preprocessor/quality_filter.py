import logging
from dataclasses import dataclass
from typing import Any

import numpy as np
import cv2

logger = logging.getLogger(__name__)


@dataclass
class QualityResult:
    passed: bool
    blur_score: float
    brightness: float
    black_ratio: float
    white_ratio: float
    issues: list[str]


class FrameQualityFilter:
    def __init__(
        self,
        blur_threshold: float = 100.0,
        min_brightness: float = 10.0,
        max_brightness: float = 245.0,
        black_ratio_threshold: float = 0.95,
        white_ratio_threshold: float = 0.95,
    ):
        self.blur_threshold = blur_threshold
        self.min_brightness = min_brightness
        self.max_brightness = max_brightness
        self.black_ratio_threshold = black_ratio_threshold
        self.white_ratio_threshold = white_ratio_threshold

    def check(self, image: np.ndarray) -> QualityResult:
        issues = []
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image

        blur_score = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        if blur_score < self.blur_threshold:
            issues.append("blurry")

        brightness = float(np.mean(gray))
        if brightness < self.min_brightness:
            issues.append("too_dark")
        elif brightness > self.max_brightness:
            issues.append("too_bright")

        black_pixels = float(np.sum(gray < 10))
        black_ratio = black_pixels / gray.size
        if black_ratio > self.black_ratio_threshold:
            issues.append("black_frame")

        white_pixels = float(np.sum(gray > 245))
        white_ratio = white_pixels / gray.size
        if white_ratio > self.white_ratio_threshold:
            issues.append("white_frame")

        return QualityResult(
            passed=len(issues) == 0,
            blur_score=blur_score,
            brightness=brightness,
            black_ratio=black_ratio,
            white_ratio=white_ratio,
            issues=issues,
        )



