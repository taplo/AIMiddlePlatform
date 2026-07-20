import asyncio
import logging
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class CollectedFrame:
    camera_id: str
    timestamp: float
    image: np.ndarray
    metadata: dict = field(default_factory=dict)
    source: str = ""


class FrameCollector:
    def __init__(self, output_dir: str | Path = "data/collected"):
        self._output = Path(output_dir)
        self._output.mkdir(parents=True, exist_ok=True)

    async def collect_from_directory(
        self,
        source_dir: str | Path,
        camera_id: str = "unknown",
        extensions: set[str] | None = None,
    ) -> list[CollectedFrame]:
        source_dir = Path(source_dir)
        if not source_dir.is_dir():
            raise ValueError(f"Source directory not found: {source_dir}")

        exts = extensions or {".jpg", ".jpeg", ".png", ".bmp"}
        frames: list[CollectedFrame] = []

        for path in sorted(source_dir.rglob("*")):
            if path.suffix.lower() in exts:
                img = cv2.imread(str(path))
                if img is not None:
                    frames.append(CollectedFrame(
                        camera_id=camera_id,
                        timestamp=path.stat().st_mtime,
                        image=img,
                        metadata={"path": str(path)},
                        source=str(path),
                    ))
                else:
                    logger.warning("Failed to read image: %s", path)

        logger.info("Collected %d frames from %s", len(frames), source_dir)
        return frames

    async def collect_from_video(
        self,
        video_path: str | Path,
        camera_id: str = "unknown",
        sample_rate: float = 1.0,
        max_frames: int = 0,
    ) -> list[CollectedFrame]:
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            raise ValueError(f"Failed to open video: {video_path}")

        frames: list[CollectedFrame] = []
        frame_idx = 0
        fps = cap.get(cv2.CAP_PROP_FPS)
        sample_interval = max(1, int(fps / sample_rate)) if sample_rate > 0 else 1

        try:
            while True:
                ret, img = cap.read()
                if not ret:
                    break

                if frame_idx % sample_interval == 0:
                    frames.append(CollectedFrame(
                        camera_id=camera_id,
                        timestamp=time.time(),
                        image=img,
                        metadata={"frame_index": frame_idx, "video_path": str(video_path)},
                        source=str(video_path),
                    ))
                    if max_frames and len(frames) >= max_frames:
                        break

                frame_idx += 1
        finally:
            cap.release()

        logger.info("Collected %d frames from video %s", len(frames), video_path)
        return frames

    async def save_frames(
        self,
        frames: list[CollectedFrame],
        subdir: str = "",
    ) -> list[Path]:
        saved: list[Path] = []
        dest = self._output / subdir if subdir else self._output
        dest.mkdir(parents=True, exist_ok=True)

        for i, frame in enumerate(frames):
            ts = datetime.fromtimestamp(frame.timestamp).strftime("%Y%m%d_%H%M%S")
            name = f"{frame.camera_id}_{ts}_{i:06d}.jpg"
            path = dest / name
            cv2.imwrite(str(path), frame.image)
            saved.append(path)

        logger.info("Saved %d frames to %s", len(saved), dest)
        return saved

    async def stream_from_camera(
        self,
        rtsp_url: str,
        camera_id: str,
        sample_interval: float = 1.0,
    ) -> AsyncIterator[CollectedFrame]:
        cap = cv2.VideoCapture(rtsp_url)
        if not cap.isOpened():
            raise ValueError(f"Failed to open RTSP stream: {rtsp_url}")

        try:
            frame_idx = 0
            while True:
                ret, img = cap.read()
                if not ret:
                    logger.warning("Stream %s: read failed, reconnecting...", camera_id)
                    await asyncio.sleep(1)
                    cap.release()
                    cap = cv2.VideoCapture(rtsp_url)
                    if not cap.isOpened():
                        logger.error("Failed to reconnect: %s", rtsp_url)
                        break
                    continue

                if frame_idx % max(1, int(30 / sample_interval)) == 0:
                    yield CollectedFrame(
                        camera_id=camera_id,
                        timestamp=time.time(),
                        image=img,
                        source=rtsp_url,
                    )

                frame_idx += 1
        finally:
            cap.release()
