import base64
import logging
import asyncio

import cv2
import numpy as np

logger = logging.getLogger(__name__)

_verify_client = None


def _get_verify_client():
    global _verify_client
    if _verify_client is None:
        from src.agent.client import QwenVLClient
        _verify_client = QwenVLClient()
    return _verify_client


def verify_handler(context: dict, input_data: dict, node_config: dict) -> dict:
    threshold = node_config.get("verify_threshold", 0.5)
    margin = node_config.get("verify_margin", 0.3)
    upper = threshold + margin

    detections = input_data.get("detections", [])
    frame_b64 = context.get("frame", "")
    if not frame_b64 or not detections:
        return {"detections": detections, "verification_count": 0}

    try:
        raw = base64.b64decode(frame_b64)
        arr = np.frombuffer(raw, dtype=np.uint8)
        frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if frame is None:
            return {"detections": detections, "verification_count": 0, "error": "decode_failed"}
    except Exception:
        return {"detections": detections, "verification_count": 0, "error": "decode_failed"}

    client = _get_verify_client()
    verified_detections = []
    v_count = 0

    for det in detections:
        conf = det.get("confidence", 0)
        if threshold <= conf < upper:
            x1, y1, x2, y2 = det.get("bbox", [0, 0, 0, 0])
            x1, y1 = max(0, x1), max(0, y1)
            x2 = min(frame.shape[1], x2)
            y2 = min(frame.shape[0], y2)
            crop = frame[y1:y2, x1:x2]
            if crop.size == 0:
                det["verified"] = False
                det["verification_error"] = "empty_crop"
                verified_detections.append(det)
                continue
            _, buf = cv2.imencode(".jpg", crop, [cv2.IMWRITE_JPEG_QUALITY, 85])
            crop_bytes = buf.tobytes()
            try:
                result = asyncio.run(client.verify(crop_bytes, det.get("label", ""), conf))
                det["verified"] = result.get("verified", False)
                if result.get("corrected_label"):
                    det["corrected_label"] = result["corrected_label"]
                det["verification_reason"] = result.get("reason", "")
            except Exception as e:
                logger.warning("VERIFY call failed: %s", e)
                det["verified"] = False
                det["verification_error"] = str(e)
            v_count += 1
        else:
            det["verified"] = True
        verified_detections.append(det)

    return {
        "detections": verified_detections,
        "verification_count": v_count,
    }
