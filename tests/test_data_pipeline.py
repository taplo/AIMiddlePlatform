import tempfile
from pathlib import Path

import cv2
import numpy as np
import pytest

from src.data.annotator import AnnotationPipeline, COCOExporter, YOLOExporter
from src.data.cleaner import FrameCleaner
from src.data.collector import CollectedFrame, FrameCollector
from src.data.pipeline import DataPipeline


def _make_test_image(h: int = 100, w: int = 100) -> np.ndarray:
    img = np.zeros((h, w, 3), dtype=np.uint8)
    img[20:80, 20:80] = (128, 128, 128)
    return img


def _make_test_video(path: Path, num_frames: int = 10) -> None:
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(str(path), fourcc, 30.0, (100, 100))
    for _ in range(num_frames):
        out.write(_make_test_image())
    out.release()


@pytest.fixture
def sample_frames():
    dets = [{"bbox": [10, 10, 50, 50], "label": "person", "confidence": 0.9}]
    frames = []
    for i in range(5):
        img = _make_test_image()
        cv2.rectangle(img, (i * 5, i * 5), (i * 5 + 10, i * 5 + 10), (255, 255, 255), -1)
        frames.append(
            CollectedFrame(
                camera_id="cam1",
                timestamp=1000.0 + i,
                image=img,
                metadata={"detections": dets},
            )
        )
    return frames


class TestFrameCollector:
    def test_collect_from_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "img1.jpg").write_bytes(cv2.imencode(".jpg", _make_test_image())[1].tobytes())
            (d / "img2.png").write_bytes(cv2.imencode(".png", _make_test_image())[1].tobytes())
            (d / "note.txt").write_text("not an image")

            collector = FrameCollector()
            import asyncio

            frames = asyncio.run(collector.collect_from_directory(d, "test_cam"))
            assert len(frames) == 2
            assert all(f.camera_id == "test_cam" for f in frames)

    def test_collect_from_video(self):
        with tempfile.TemporaryDirectory() as tmp:
            video_path = Path(tmp) / "test.mp4"
            _make_test_video(video_path, num_frames=20)

            collector = FrameCollector()
            import asyncio

            frames = asyncio.run(collector.collect_from_video(video_path, "cam1", sample_rate=10))
            assert len(frames) > 0
            assert all(f.camera_id == "cam1" for f in frames)

    def test_save_frames(self):
        with tempfile.TemporaryDirectory() as tmp:
            collector = FrameCollector(output_dir=tmp)
            frames = [CollectedFrame(camera_id="cam1", timestamp=1000.0, image=_make_test_image()) for _ in range(3)]
            import asyncio

            paths = asyncio.run(collector.save_frames(frames))
            assert len(paths) == 3
            assert all(p.exists() for p in paths)


class TestFrameCleaner:
    def test_clean_all_pass(self, sample_frames):
        cleaner = FrameCleaner()
        cleaned, report = cleaner.clean(sample_frames)
        assert len(cleaned) == 5
        assert report.total == 5
        assert report.passed == 5

    def test_clean_removes_duplicates(self):
        img = _make_test_image()
        frames = [
            CollectedFrame(camera_id="cam1", timestamp=1000.0, image=img.copy()),
            CollectedFrame(camera_id="cam1", timestamp=1001.0, image=img.copy()),
            CollectedFrame(camera_id="cam1", timestamp=1002.0, image=img.copy()),
        ]
        cleaner = FrameCleaner()
        cleaned, report = cleaner.clean(frames)
        assert len(cleaned) == 1
        assert report.removed_duplicate == 2

    def test_clean_removes_black_frame(self):
        black = np.zeros((100, 100, 3), dtype=np.uint8)
        frames = [CollectedFrame(camera_id="cam1", timestamp=1000.0, image=black)]
        cleaner = FrameCleaner()
        cleaned, report = cleaner.clean(frames)
        assert len(cleaned) == 0
        assert report.removed_black_frame > 0

    def test_clean_removes_blurry_frame(self):
        blurry = np.ones((100, 100, 3), dtype=np.uint8) * 128
        frames = [CollectedFrame(camera_id="cam1", timestamp=1000.0, image=blurry)]
        cleaner = FrameCleaner()
        cleaned, report = cleaner.clean(frames)
        assert len(cleaned) == 0


class TestCOCOExporter:
    def test_export(self, sample_frames):
        with tempfile.TemporaryDirectory() as tmp:
            exporter = COCOExporter(tmp)
            path = exporter.export(sample_frames, "test_dataset")
            assert path.exists()
            import json

            data = json.loads(path.read_text(encoding="utf-8"))
            assert len(data["images"]) == 5
            assert len(data["annotations"]) == 5
            assert len(data["categories"]) == 1


class TestYOLOExporter:
    def test_export(self, sample_frames):
        with tempfile.TemporaryDirectory() as tmp:
            exporter = YOLOExporter(tmp)
            path = exporter.export(sample_frames, "test_dataset")
            assert path.exists()
            names_file = Path(tmp) / "test_dataset.names"
            assert names_file.exists()


class TestDataPipeline:
    def test_run_from_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            img_dir = Path(tmp) / "source"
            img_dir.mkdir()
            for i in range(5):
                img_path = img_dir / f"img_{i}.jpg"
                img_path.write_bytes(cv2.imencode(".jpg", _make_test_image())[1].tobytes())

            pipeline = DataPipeline(
                annotator=AnnotationPipeline(Path(tmp) / "exports"),
            )
            import asyncio

            result = asyncio.run(
                pipeline.run_from_directory(
                    source_dir=img_dir,
                    camera_id="test_cam",
                    dataset_name="test_ds",
                )
            )
            assert result.collected == 5
            assert result.cleaned > 0
            assert "coco" in result.exports
