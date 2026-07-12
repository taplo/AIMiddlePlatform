import numpy as np
import pytest

from src.frame_preprocessor.processor import FramePreprocessor
from src.frame_preprocessor.quality_filter import FrameQualityFilter
from src.frame_preprocessor.adaptive_sampler import AdaptiveFrameSampler
from src.frame_preprocessor.yolo_world import YOLOWorldSceneClassifier


def test_preprocessor_good_frame_processes() -> None:
    p = FramePreprocessor()
    img = np.random.randint(30, 220, (480, 640, 3), dtype=np.uint8)
    decision = p.process(img, "cam_1")
    assert decision.action == "process"
    assert decision.rejection_reason is None
    assert decision.quality is not None
    assert decision.quality.passed


def test_preprocessor_blurry_frame_rejects() -> None:
    quality = FrameQualityFilter(blur_threshold=99999.0)
    p = FramePreprocessor(quality_filter=quality)
    img = np.random.randint(0, 255, (100, 100, 3), dtype=np.uint8)
    decision = p.process(img, "cam_1")
    assert decision.action == "reject"
    assert decision.rejection_reason is not None
    assert "quality" in decision.rejection_reason


def test_preprocessor_duplicate_frame_skips() -> None:
    quality = FrameQualityFilter()
    sampler = AdaptiveFrameSampler(mse_threshold_low=0.5)
    p = FramePreprocessor(quality_filter=quality, sampler=sampler)

    img = np.random.randint(0, 256, (200, 200, 3), dtype=np.uint8)
    first = p.process(img, "cam_1")
    assert first.action == "process"

    second = p.process(img, "cam_1")
    assert second.action == "skip"
    assert second.rejection_reason == "sampling_duplicate"


def test_preprocessor_quality_takes_priority_over_sampling() -> None:
    quality = FrameQualityFilter(blur_threshold=99999.0)
    sampler = AdaptiveFrameSampler(mse_threshold_low=0.5)
    p = FramePreprocessor(quality_filter=quality, sampler=sampler)

    img = np.ones((100, 100, 3), dtype=np.uint8) * 128
    p.process(img, "cam_1")
    decision = p.process(img, "cam_1")
    assert decision.action == "reject"


def test_preprocessor_different_cameras_independent() -> None:
    p = FramePreprocessor()
    img = np.random.randint(0, 256, (200, 200, 3), dtype=np.uint8)

    p.process(img, "cam_a")
    decision_a = p.process(img, "cam_a")
    assert decision_a.action == "skip"

    decision_b = p.process(img, "cam_b")
    assert decision_b.action == "process"


def test_preprocessor_scene_classifier_available() -> None:
    yolo = YOLOWorldSceneClassifier(model_dir="/tmp/nonexistent")
    p = FramePreprocessor(scene_classifier=yolo)
    img = np.random.randint(30, 220, (100, 100, 3), dtype=np.uint8)
    decision = p.process(img, "cam_1")
    assert decision.scene is not None
