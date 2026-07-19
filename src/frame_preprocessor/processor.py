import logging
from dataclasses import dataclass
from typing import Any

import numpy as np

from src.frame_preprocessor.adaptive_sampler import AdaptiveFrameSampler, SamplingResult
from src.frame_preprocessor.quality_filter import FrameQualityFilter, QualityResult
from src.frame_preprocessor.yolo_world import YOLOWorldSceneClassifier

logger = logging.getLogger(__name__)


@dataclass
class PreprocessorDecision:
    action: str
    task_id: str | None
    rejection_reason: str | None
    quality: QualityResult | None
    sampling: SamplingResult | None
    scene: dict[str, Any] | None


class FramePreprocessor:
    def __init__(
        self,
        quality_filter: FrameQualityFilter | None = None,
        sampler: AdaptiveFrameSampler | None = None,
        scene_classifier: YOLOWorldSceneClassifier | None = None,
    ):
        self.quality = quality_filter or FrameQualityFilter()
        self.sampler = sampler or AdaptiveFrameSampler()
        self.scene = scene_classifier or YOLOWorldSceneClassifier()

    def process(self, image: np.ndarray, camera_id: str) -> PreprocessorDecision:
        quality_result = self.quality.check(image)
        if not quality_result.passed:
            reason = "_".join(quality_result.issues)
            logger.info("Frame from %s rejected: %s", camera_id, reason)
            return PreprocessorDecision(
                action="reject",
                task_id=None,
                rejection_reason=f"quality_{reason}",
                quality=quality_result,
                sampling=None,
                scene=None,
            )

        sampling_result = self.sampler.should_process(camera_id, image)
        if sampling_result.decision == "skip":
            logger.debug("Frame from %s skipped by sampler (mse=%.2f)", camera_id, sampling_result.mse)
            return PreprocessorDecision(
                action="skip",
                task_id=None,
                rejection_reason="sampling_duplicate",
                quality=quality_result,
                sampling=sampling_result,
                scene=None,
            )

        scene_result = self.scene.classify(image)

        return PreprocessorDecision(
            action="process",
            task_id=None,
            rejection_reason=None,
            quality=quality_result,
            sampling=sampling_result,
            scene=scene_result,
        )
