import hashlib
import logging
from dataclasses import dataclass

import cv2
import numpy as np

from src.data.collector import CollectedFrame
from src.frame_preprocessor.quality_filter import FrameQualityFilter

logger = logging.getLogger(__name__)


@dataclass
class CleaningReport:
    total: int = 0
    passed: int = 0
    removed_blurry: int = 0
    removed_duplicate: int = 0
    removed_low_quality: int = 0
    removed_black_frame: int = 0
    removed_white_frame: int = 0


class FrameCleaner:
    def __init__(
        self,
        quality_filter: FrameQualityFilter | None = None,
        similarity_threshold: float = 0.95,
    ):
        self._quality = quality_filter or FrameQualityFilter()
        self._similarity_threshold = similarity_threshold
        self._seen_hashes: set[str] = set()

    def _phash(self, image: np.ndarray, hash_size: int = 8) -> str:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
        resized = cv2.resize(gray, (hash_size + 1, hash_size))
        diff = resized[:, 1:] > resized[:, :-1]
        bits = diff.flatten()
        chars = []
        for i in range(0, len(bits), 4):
            val = 0
            for j in range(4):
                if i + j < len(bits):
                    val |= int(bits[i + j]) << (3 - j)
            chars.append(format(val, "x"))
        return "".join(chars)

    def _dhash(self, image: np.ndarray, hash_size: int = 8) -> str:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
        resized = cv2.resize(gray, (hash_size + 1, hash_size))
        diff = resized[1:, :] > resized[:-1, :]
        bits = diff.flatten()
        chars = []
        for i in range(0, len(bits), 4):
            val = 0
            for j in range(4):
                if i + j < len(bits):
                    val |= int(bits[i + j]) << (3 - j)
            chars.append(format(val, "x"))
        return "".join(chars)

    def _sha256(self, image: np.ndarray) -> str:
        return hashlib.sha256(image.tobytes()).hexdigest()

    def clean(self, frames: list[CollectedFrame]) -> tuple[list[CollectedFrame], CleaningReport]:
        report = CleaningReport(total=len(frames))
        cleaned: list[CollectedFrame] = []
        self._seen_hashes.clear()

        for frame in frames:
            quality = self._quality.check(frame.image)

            if "black_frame" in quality.issues:
                report.removed_black_frame += 1
                continue
            if "white_frame" in quality.issues:
                report.removed_white_frame += 1
                continue
            if "blurry" in quality.issues:
                report.removed_blurry += 1
                continue
            if not quality.passed:
                report.removed_low_quality += 1
                continue

            frame_hash = self._sha256(frame.image)
            if frame_hash in self._seen_hashes:
                report.removed_duplicate += 1
                continue
            self._seen_hashes.add(frame_hash)

            cleaned.append(frame)

        report.passed = len(cleaned)
        logger.info(
            "Cleaning: %d total -> %d passed "
            "(blurry=%d, duplicate=%d, low_quality=%d, black=%d, white=%d)",
            report.total, report.passed,
            report.removed_blurry, report.removed_duplicate,
            report.removed_low_quality, report.removed_black_frame,
            report.removed_white_frame,
        )
        return cleaned, report
