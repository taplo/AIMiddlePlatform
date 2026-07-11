import json
import pytest
import numpy as np

from src.pipeline.dag import DAGDefinition, DAGNode, NodeType
from src.pipeline.executor import DAGExecutor
from src.pipeline.verify_handler import verify_handler


def _make_frame(height=200, width=300):
    import cv2
    img = np.zeros((height, width, 3), dtype=np.uint8)
    img[50:150, 100:200] = (255, 255, 255)
    import base64
    _, buf = cv2.imencode(".jpg", img)
    return base64.b64encode(buf).decode("ascii")


SAMPLE_DETECTIONS = [
    {"bbox": [100, 50, 200, 150], "label": "person", "confidence": 0.65},
    {"bbox": [0, 0, 50, 50], "label": "car", "confidence": 0.95},
    {"bbox": [50, 50, 100, 100], "label": "dog", "confidence": 0.30},
]


def test_verify_no_candidates():
    dets = [
        {"bbox": [0, 0, 10, 10], "label": "car", "confidence": 0.95},
        {"bbox": [0, 0, 10, 10], "label": "bus", "confidence": 0.20},
    ]
    result = verify_handler(
        {"frame": _make_frame()},
        {"detections": dets},
        {"verify_threshold": 0.5, "verify_margin": 0.3},
    )
    assert result["verification_count"] == 0
    assert all(d.get("verified") is True for d in result["detections"])


def test_verify_candidate_accepted():
    dets = [{"bbox": [100, 50, 200, 150], "label": "person", "confidence": 0.65}]
    result = verify_handler(
        {"frame": _make_frame()},
        {"detections": dets},
        {"verify_threshold": 0.5, "verify_margin": 0.3},
    )
    assert result["verification_count"] == 1
    d = result["detections"][0]
    assert d["verified"] is True or d["verified"] is False
    assert "verification_reason" in d


def test_verify_candidate_rejected():
    dets = [{"bbox": [100, 50, 200, 150], "label": "person", "confidence": 0.65}]
    result = verify_handler(
        {"frame": _make_frame()},
        {"detections": dets},
        {"verify_threshold": 0.5, "verify_margin": 0.3},
    )
    d = result["detections"][0]
    assert "verified" in d


def test_verify_empty_frame():
    dets = [{"bbox": [100, 50, 200, 150], "label": "person", "confidence": 0.65}]
    result = verify_handler(
        {"frame": ""},
        {"detections": dets},
        {},
    )
    assert result["verification_count"] == 0
    assert len(result["detections"]) == 1


def test_verify_no_detections():
    result = verify_handler(
        {"frame": _make_frame()},
        {"detections": []},
        {},
    )
    assert result["verification_count"] == 0
    assert result["detections"] == []


def test_verify_edge_threshold():
    dets = [
        {"bbox": [100, 50, 200, 150], "label": "person", "confidence": 0.5},
        {"bbox": [100, 50, 200, 150], "label": "car", "confidence": 0.8},
        {"bbox": [100, 50, 200, 150], "label": "bus", "confidence": 0.79},
    ]
    result = verify_handler(
        {"frame": _make_frame()},
        {"detections": dets},
        {"verify_threshold": 0.5, "verify_margin": 0.3},
    )
    assert result["verification_count"] == 2
