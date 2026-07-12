import base64
import json
import logging
import asyncio
import time

import cv2
import numpy as np

logger = logging.getLogger(__name__)

_verify_client = None
_verify_cache = None
_verify_hasher = None


def _get_verify_client():
    global _verify_client
    if _verify_client is None:
        from src.agent.client import QwenVLClient
        _verify_client = QwenVLClient()
    return _verify_client


_verify_ttl = 60


def _get_verify_cache():
    global _verify_cache, _verify_ttl
    if _verify_cache is None:
        from src.core.config import settings
        if not settings.get("result_cache.enabled", True):
            return None
        _verify_ttl = settings.get("result_cache.ttl_seconds", 60)
        import redis as sync_redis
        redis_url = settings.get("queue.redis_url", "redis://localhost:6379/0")
        _verify_cache = sync_redis.from_url(redis_url)
    return _verify_cache


def _get_verify_hasher():
    global _verify_hasher
    if _verify_hasher is None:
        from src.cache.frame_hasher import FrameHasher
        _verify_hasher = FrameHasher()
    return _verify_hasher


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
            context_str = f"verify:{det.get('label', '')}"
            cache_hit = False
            try:
                cache = _get_verify_cache()
                hasher = _get_verify_hasher()
                frame_hash = hasher.compute(raw)
                exact_key = f"cache:result:{context.get('camera_id', '')}:{frame_hash}"
                cached = cache.get(exact_key)
                if cached:
                    cached_data = json.loads(cached)
                    entry_ctx = cached_data.get("context_hash", "")
                    if entry_ctx == context_str:
                        result = cached_data["result"]
                        det["verified"] = result.get("verified", False)
                        if result.get("corrected_label"):
                            det["corrected_label"] = result["corrected_label"]
                        det["verification_reason"] = result.get("reason", "")
                        det["verification_cache_hit"] = True
                        cache_hit = True
            except Exception:
                logger.debug("Cache lookup failed, falling through to LLM", exc_info=True)

            if cache_hit:
                verified_detections.append(det)
                v_count += 1
                continue

            try:
                result = asyncio.run(client.verify(crop_bytes, det.get("label", ""), conf))
                det["verified"] = result.get("verified", False)
                if result.get("corrected_label"):
                    det["corrected_label"] = result["corrected_label"]
                det["verification_reason"] = result.get("reason", "")

                try:
                    if cache:
                        cache_entry = json.dumps({
                            "result": result,
                            "created_at": time.time(),
                            "context_hash": context_str,
                        })
                        cache.set(exact_key, cache_entry, ex=_verify_ttl)
                        camera_set_key = f"cache:camera:{context.get('camera_id', '')}:hashes"
                        cache.zadd(camera_set_key, {f"{frame_hash}:{context_str}": time.time()})
                        cache.expire(camera_set_key, _verify_ttl)
                        cache.incr("cache:stats:misses")
                except Exception:
                    logger.debug("Cache store failed", exc_info=True)
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
