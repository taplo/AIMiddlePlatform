import numpy as np
import pytest

from src.frame_preprocessor.adaptive_sampler import AdaptiveFrameSampler


def test_sampler_first_frame_always_processes() -> None:
    s = AdaptiveFrameSampler()
    img = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
    result = s.should_process("cam_1", img)
    assert result.decision == "process"


def test_sampler_identical_frame_skips() -> None:
    s = AdaptiveFrameSampler(mse_threshold_low=0.5)
    img = np.random.randint(100, 110, (480, 640, 3), dtype=np.uint8)
    s.should_process("cam_1", img)
    result = s.should_process("cam_1", img)
    assert result.decision == "skip"


def test_sampler_very_different_frame_processes() -> None:
    s = AdaptiveFrameSampler(mse_threshold_high=3.0)
    img1 = np.zeros((480, 640, 3), dtype=np.uint8)
    img2 = np.ones((480, 640, 3), dtype=np.uint8) * 255
    s.should_process("cam_1", img1)
    result = s.should_process("cam_1", img2)
    assert result.decision == "process"


def test_sampler_separate_camera_state() -> None:
    s = AdaptiveFrameSampler(mse_threshold_low=10.0)
    img = np.random.randint(100, 110, (480, 640, 3), dtype=np.uint8)
    s.should_process("cam_a", img)
    result_a = s.should_process("cam_a", img)
    result_b = s.should_process("cam_b", img)
    assert result_a.decision == "skip"
    assert result_b.decision == "process"


def test_sampler_returns_sampling_metrics() -> None:
    s = AdaptiveFrameSampler()
    img = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
    first = s.should_process("cam_1", img)
    assert first.mse == float("inf")
    second = s.should_process("cam_1", img)
    assert second.mse >= 0


def test_sampler_decay_expires_old_frames() -> None:
    s = AdaptiveFrameSampler(mse_threshold_low=10.0, decay_seconds=0.001)
    img = np.random.randint(100, 110, (480, 640, 3), dtype=np.uint8)
    s.should_process("cam_1", img)
    import time
    time.sleep(0.005)
    result = s.should_process("cam_1", img)
    assert result.decision == "process"


def test_sampler_grayscale_input() -> None:
    s = AdaptiveFrameSampler()
    img = np.random.randint(0, 255, (480, 640), dtype=np.uint8)
    result = s.should_process("cam_1", img)
    assert result.decision == "process"


def test_sampler_mse_values_are_reasonable() -> None:
    s = AdaptiveFrameSampler()
    img1 = np.zeros((100, 100, 3), dtype=np.uint8)
    s.should_process("cam_a", img1)
    img2 = np.ones((100, 100, 3), dtype=np.uint8) * 255
    result = s.should_process("cam_a", img2)
    assert result.mse > 50000
