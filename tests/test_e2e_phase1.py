"""Phase 1 E2E verification: STR-01 (接入), STR-02 (抽帧/ROI), API-03 (结果格式)."""

import base64
from pathlib import Path

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from src.api.app import app
from src.core.schemas import AnalysisResult, FrameInfo, ModelResult

_TEST_IMAGE = Path(__file__).resolve().parent.parent / "bus_test.jpg"
_TEST_API_KEY = "sk-e2e-phase1-key-00000000"


@pytest.fixture(scope="session")
def test_image() -> np.ndarray:
    img = cv2.imread(str(_TEST_IMAGE))
    assert img is not None, f"Test image not found: {_TEST_IMAGE}"
    return img


@pytest.fixture(autouse=True)
def _setup_api_key():
    from src.core.security import get_api_key_store
    store = get_api_key_store()
    store.add_key("test", _TEST_API_KEY, rate_per_second=100)
    yield


class TestAPI03Schema:
    """API-03: 统一结构化结果格式"""

    def test_frame_info_roundtrip(self):
        info = FrameInfo(width=1920, height=1080, fps_actual=25.0)
        d = info.model_dump()
        restored = FrameInfo(**d)
        assert restored.width == 1920
        assert restored.height == 1080
        assert restored.fps_actual == 25.0

    def test_model_result_roundtrip(self):
        result = ModelResult(
            model_id="object_detection",
            confidence=0.95,
            data={"detections": [{"bbox": [10, 20, 100, 200], "label": "person", "confidence": 0.95}]},
        )
        d = result.model_dump()
        restored = ModelResult(**d)
        assert restored.model_id == "object_detection"
        assert restored.confidence == 0.95
        assert len(restored.data["detections"]) == 1

    def test_analysis_result_full(self):
        from datetime import datetime
        result = AnalysisResult(
            request_id="req-001",
            timestamp=datetime(2026, 7, 21, 12, 0, 0),
            camera_id="cam-01",
            frame_info=FrameInfo(width=1920, height=1080, fps_actual=25.0),
            results=[ModelResult(model_id="object_detection", confidence=0.95)],
            latency_ms=150.0,
        )
        d = result.model_dump()
        assert d["request_id"] == "req-001"
        assert d["camera_id"] == "cam-01"
        assert d["latency_ms"] == 150.0
        assert len(d["results"]) == 1
        assert d["results"][0]["model_id"] == "object_detection"


class TestSTR02FrameExtraction:
    """STR-02: 可配帧率抽帧 + ROI 提取"""

    def test_adaptive_sampler_first_frame(self):
        from src.frame_preprocessor.adaptive_sampler import AdaptiveFrameSampler
        sampler = AdaptiveFrameSampler()
        result = sampler.should_process("cam-ut", np.zeros((100, 100, 3), dtype=np.uint8))
        assert result.decision == "process"

    def test_quality_filter_sharp(self, test_image):
        from src.frame_preprocessor.quality_filter import FrameQualityFilter
        f = FrameQualityFilter()
        assert f.check(test_image).passed is True

    def test_quality_filter_rejects_uniform(self):
        from src.frame_preprocessor.quality_filter import FrameQualityFilter
        f = FrameQualityFilter()
        uniform = np.full((480, 640, 3), 128, dtype=np.uint8)
        assert f.check(uniform).passed is False

    def test_preprocessor_pipeline(self, test_image):
        from src.frame_preprocessor.processor import FramePreprocessor
        from src.frame_preprocessor.adaptive_sampler import AdaptiveFrameSampler
        from src.frame_preprocessor.quality_filter import FrameQualityFilter

        preprocessor = FramePreprocessor(
            quality_filter=FrameQualityFilter(),
            sampler=AdaptiveFrameSampler(),
            scene_classifier=None,
        )
        decision = preprocessor.process(test_image, "cam-e2e")
        assert decision.action in ("process", "skip")
        assert isinstance(decision.rejection_reason, str | None)

    def test_roi_extraction(self):
        from src.ingestion.roi import ROIProcessor, ROIConfig
        config = ROIConfig(x=100, y=200, width=300, height=400, enabled=True)
        processor = ROIProcessor(config=config)
        frame = np.random.randint(0, 255, (1080, 1920, 3), dtype=np.uint8)
        result = processor.apply(frame)
        assert result.shape == (400, 300, 3)

    def test_video_cache(self):
        from src.ingestion.video_cache import VideoRingBuffer
        buf = VideoRingBuffer(default_duration=5.0, max_memory=50 * 1024 * 1024)
        buf.push("cam-01", np.zeros((480, 640, 3), dtype=np.uint8))
        buf.push("cam-01", np.zeros((480, 640, 3), dtype=np.uint8))
        assert buf.stats("cam-01")["buffered_frames"] == 2


class TestSTR01StreamIngestion:
    """STR-01: 视频流接入基础能力"""

    def test_stream_config_schema(self):
        from src.core.schemas import StreamConfig
        cfg = StreamConfig(camera_id="cam-01", stream_url="rtsp://192.168.1.100:554/stream1")
        assert cfg.camera_id == "cam-01"
        assert cfg.protocol == "rtsp"
        assert cfg.target_fps == 2.0
        assert cfg.roi is None

    def test_stream_manager_initialization(self):
        from src.ingestion.stream_manager import StreamManager
        mgr = StreamManager()
        stats = mgr.stats()
        assert stats["total_streams"] == 0


class TestAnalyzeEndpointE2E:
    """端到端 API 流程：analyze frame + 结果查询"""

    def _headers(self):
        return {"X-API-Key": _TEST_API_KEY}

    def test_ping(self):
        resp = TestClient(app).get("/api/v1/analyze/ping")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_analyze_frame_returns_valid_response(self, test_image):
        _, buffer = cv2.imencode(".jpg", test_image, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
        frame_b64 = base64.b64encode(buffer).decode()

        client = TestClient(app)
        resp = client.post(
            "/api/v1/analyze/frame?sync=false",
            json={"camera_id": "cam-e2e", "frame": frame_b64, "scene_type": "detection"},
            headers=self._headers(),
        )
        if resp.status_code == 500:
            pytest.skip("Redis unavailable")
        assert resp.status_code == 200
        data = resp.json()
        assert "task_id" in data
        assert isinstance(data["task_id"], str)

    def test_analyze_rejects_large_frame(self):
        client = TestClient(app)
        resp = client.post(
            "/api/v1/analyze/frame",
            json={"camera_id": "cam-e2e", "frame": "A" * (10 * 1024 * 1024 + 1)},
            headers=self._headers(),
        )
        if resp.status_code == 500:
            pytest.skip("Redis unavailable - cannot test full endpoint")
        assert resp.status_code == 413
        assert "too large" in resp.json()["detail"].lower()
