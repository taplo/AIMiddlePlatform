import numpy as np

from src.frame_preprocessor.quality_filter import FrameQualityFilter


def test_quality_filter_good_frame_passes() -> None:
    f = FrameQualityFilter()
    img = np.random.randint(30, 220, (480, 640, 3), dtype=np.uint8)
    result = f.check(img)
    assert result.passed is True
    assert result.issues == []


def test_quality_filter_blurry_detected() -> None:
    f = FrameQualityFilter(blur_threshold=100.0)
    img = np.ones((480, 640, 3), dtype=np.uint8) * 128
    result = f.check(img)
    assert "blurry" in result.issues
    assert result.passed is False


def test_quality_filter_too_dark() -> None:
    f = FrameQualityFilter(min_brightness=10.0)
    img = np.ones((480, 640, 3), dtype=np.uint8) * 2
    result = f.check(img)
    assert "too_dark" in result.issues
    assert result.passed is False


def test_quality_filter_too_bright() -> None:
    f = FrameQualityFilter(max_brightness=245.0)
    img = np.ones((480, 640, 3), dtype=np.uint8) * 250
    result = f.check(img)
    assert "too_bright" in result.issues
    assert result.passed is False


def test_quality_filter_black_frame() -> None:
    f = FrameQualityFilter(black_ratio_threshold=0.95)
    img = np.zeros((480, 640, 3), dtype=np.uint8)
    result = f.check(img)
    assert "black_frame" in result.issues or "too_dark" in result.issues
    assert result.passed is False


def test_quality_filter_white_frame() -> None:
    f = FrameQualityFilter(white_ratio_threshold=0.95)
    img = np.ones((480, 640, 3), dtype=np.uint8) * 255
    result = f.check(img)
    assert "white_frame" in result.issues
    assert result.passed is False


def test_quality_filter_scores_are_finite() -> None:
    f = FrameQualityFilter()
    img = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
    result = f.check(img)
    assert result.blur_score >= 0
    assert 0 <= result.brightness <= 255
    assert 0 <= result.black_ratio <= 1
    assert 0 <= result.white_ratio <= 1


def test_quality_filter_grayscale_input() -> None:
    f = FrameQualityFilter()
    img = np.random.randint(30, 220, (480, 640), dtype=np.uint8)
    result = f.check(img)
    assert result.blur_score >= 0


def test_quality_filter_custom_thresholds() -> None:
    f = FrameQualityFilter(blur_threshold=99999.0)
    img = np.random.randint(0, 255, (100, 100, 3), dtype=np.uint8)
    result = f.check(img)
    assert result.passed is False
    assert "blurry" in result.issues
