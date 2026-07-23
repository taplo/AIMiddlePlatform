import hashlib
import json
import logging
from dataclasses import dataclass

import cv2
import numpy as np

from src.data.collector import CollectedFrame
from src.frame_preprocessor.quality_filter import FrameQualityFilter

logger = logging.getLogger(__name__)


def _phash(image: np.ndarray, hash_size: int = 8) -> str:
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


def _hamming(a: str, b: str) -> float:
    """Normalized Hamming distance between two hex hash strings."""
    if len(a) != len(b):
        return 1.0
    a_bits = int(a, 16)
    b_bits = int(b, 16)
    diff = a_bits ^ b_bits
    bits_set = 0
    while diff:
        bits_set += diff & 1
        diff >>= 1
    return bits_set / (len(a) * 4)


@dataclass
class CleaningReport:
    total: int = 0
    passed: int = 0
    removed_blurry: int = 0
    removed_duplicate: int = 0
    removed_near_duplicate: int = 0
    removed_low_quality: int = 0
    removed_black_frame: int = 0
    removed_white_frame: int = 0
    removed_agent_duplicate: int = 0


class FrameCleaner:
    def __init__(
        self,
        quality_filter: FrameQualityFilter | None = None,
        hash_threshold: float = 0.15,
    ):
        self._quality = quality_filter or FrameQualityFilter()
        self._hash_threshold = hash_threshold
        self._seen_hashes: set[str] = set()
        self._seen_phash: list[str] = []

    def _sha256(self, image: np.ndarray) -> str:
        return hashlib.sha256(image.tobytes()).hexdigest()

    def clean(self, frames: list[CollectedFrame]) -> tuple[list[CollectedFrame], CleaningReport]:
        report = CleaningReport(total=len(frames))
        cleaned: list[CollectedFrame] = []
        self._seen_hashes.clear()
        self._seen_phash.clear()

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

            ph = _phash(frame.image)
            is_near_dup = any(
                _hamming(ph, seen) < self._hash_threshold
                for seen in self._seen_phash
            )
            if is_near_dup:
                report.removed_near_duplicate += 1
                continue
            self._seen_phash.append(ph)

            cleaned.append(frame)

        report.passed = len(cleaned)
        logger.info(
            "Cleaning: %d total -> %d passed "
            "(blurry=%d, dup=%d, near_dup=%d, low_q=%d, black=%d, white=%d)",
            report.total, report.passed,
            report.removed_blurry, report.removed_duplicate,
            report.removed_near_duplicate, report.removed_low_quality,
            report.removed_black_frame, report.removed_white_frame,
        )
        return cleaned, report


class AgentPairCleaner:
    """Deduplicates agent input/output pairs by frame and result content."""

    def __init__(self, result_similarity_threshold: float = 0.9):
        self._result_similarity_threshold = result_similarity_threshold
        self._frame_cleaner = FrameCleaner()

    def _result_signature(self, result: dict) -> str:
        """Extract a hashable signature from agent result for dedup."""
        relevant = {}
        for key in ("scene_type", "objects", "anomalies", "summary", "path"):
            if key in result:
                relevant[key] = result.get(key)
        return hashlib.sha256(
            json.dumps(relevant, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()

    def clean_pairs(
        self,
        images: list[np.ndarray],
        contexts: list[dict],
        results: list[dict],
    ) -> tuple[list[np.ndarray], list[dict], list[dict], CleaningReport]:
        report = CleaningReport(total=len(images))
        frames = [
            CollectedFrame(camera_id="", timestamp=float(i), image=img)
            for i, img in enumerate(images)
        ]

        cleaned_frames, frame_report = self._frame_cleaner.clean(frames)
        report.removed_blurry = frame_report.removed_blurry
        report.removed_duplicate = frame_report.removed_duplicate
        report.removed_near_duplicate = frame_report.removed_near_duplicate
        report.removed_low_quality = frame_report.removed_low_quality
        report.removed_black_frame = frame_report.removed_black_frame
        report.removed_white_frame = frame_report.removed_white_frame

        kept_indices = {
            int(f.timestamp) for f in cleaned_frames
        }

        seen_result_sigs: set[str] = set()
        out_images: list[np.ndarray] = []
        out_contexts: list[dict] = []
        out_results: list[dict] = []

        for i in range(len(images)):
            if i not in kept_indices:
                continue

            sig = self._result_signature(results[i])
            if sig in seen_result_sigs:
                report.removed_agent_duplicate += 1
                continue
            seen_result_sigs.add(sig)

            out_images.append(images[i])
            out_contexts.append(contexts[i])
            out_results.append(results[i])

        report.passed = len(out_images)
        logger.info(
            "Agent pair cleaning: %d total -> %d passed "
            "(removed_agent_dup=%d)",
            report.total, report.passed,
            report.removed_agent_duplicate,
        )
        return out_images, out_contexts, out_results, report
