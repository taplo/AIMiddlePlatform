import numpy as np

from src.ingestion.roi import ROIConfig, ROIProcessor


def test_roi_disabled() -> None:
    config = ROIConfig(enabled=False)
    proc = ROIProcessor(config)
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    result = proc.apply(frame)
    assert result.shape == (100, 100, 3)


def test_roi_enabled() -> None:
    config = ROIConfig(x=10, y=10, width=50, height=50, enabled=True)
    proc = ROIProcessor(config)
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    result = proc.apply(frame)
    assert result.shape == (50, 50, 3)
