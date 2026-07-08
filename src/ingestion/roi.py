from dataclasses import dataclass

import cv2
import numpy as np


@dataclass
class ROIConfig:
    x: int = 0
    y: int = 0
    width: int = 0
    height: int = 0
    enabled: bool = False

    @classmethod
    def from_dict(cls, data: dict | None) -> "ROIConfig":
        if data is None:
            return cls()
        return cls(
            x=data.get("x", 0),
            y=data.get("y", 0),
            width=data.get("width", 0),
            height=data.get("height", 0),
            enabled=data.get("enabled", True),
        )


class ROIProcessor:
    def __init__(self, config: ROIConfig) -> None:
        self.config = config

    def apply(self, frame: np.ndarray) -> np.ndarray:
        if not self.config.enabled:
            return frame
        h, w = frame.shape[:2]
        x = min(self.config.x, w - 1)
        y = min(self.config.y, h - 1)
        rw = min(self.config.width, w - x)
        rh = min(self.config.height, h - y)
        if rw <= 0 or rh <= 0:
            return frame
        return frame[y : y + rh, x : x + rw]
