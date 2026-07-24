import asyncio
import base64
import logging

import cv2
import numpy as np

from src.resilience.retry import retry_with_backoff

logger = logging.getLogger(__name__)

_verify_client = None
_verify_cache = None
_verify_hasher = None


def _get_verify_client():
    global _verify_client
    if _verify_client is None:
        from src.agent.agent_config import get_config_manager
        _verify_client = get_config_manager().get_client()
    return _verify_client


def _get_verify_hasher():
    global _verify_hasher
    if _verify_hasher is None:
        from src.cache.frame_hasher import FrameHasher
        _verify_hasher = FrameHasher()
    return _verify_hasher


async def _get_result_cache():
    global _verify_cache
    if _verify_cache is None:
        from src.core.config import settings
        if not settings.get("result_cache.enabled", True):
            return None
        from src.cache.result_cache import ResultCache
        from src.core.redis_client import get_redis
        redis = await get_redis()
        if redis is None:
            return None
        _verify_cache = ResultCache(redis)
    return _verify_cache


def _decode_frame(frame_b64: str):
    try:
        raw = base64.b64decode(frame_b64)
        arr = np.frombuffer(raw, dtype=np.uint8)
        return cv2.imdecode(arr, cv2.IMREAD_COLOR), raw
    except Exception:
        return None, None


async def _verify_one_detection(client, cache, frame, det, frame_hash, cache_key, camera_id):
    x1, y1, x2, y2 = det.get("bbox", [0, 0, 0, 0])
    x1, y1 = max(0, x1), max(0, y1)
    x2 = min(frame.shape[1], x2)
    y2 = min(frame.shape[0], y2)
    crop = frame[y1:y2, x1:x2]
    if crop.size == 0:
        det["verified"] = False
        det["verification_error"] = "empty_crop"
        return

    _, buf = cv2.imencode(".jpg", crop, [cv2.IMWRITE_JPEG_QUALITY, 85])
    crop_bytes = buf.tobytes()
    try:
        result = await client.verify(crop_bytes, det.get("label", ""), det.get("confidence", 0))
        det["verified"] = result.get("verified", False)
        if result.get("corrected_label"):
            det["corrected_label"] = result["corrected_label"]
        det["verification_reason"] = result.get("reason", "")
    except Exception as e:
        logger.warning("VERIFY call failed: %s", e)
        det["verified"] = False
        det["verification_error"] = str(e)
        return

    if cache:
        try:
            await cache.set(camera_id, frame_hash, {"verified": det["verified"], "reason": det.get("verification_reason", "")}, cache_key)
        except Exception:
            logger.debug("Cache store failed", exc_info=True)


def _check_assertions(detections: list[dict], config: dict) -> str | None:
    min_count = config.get("assert_min_detections", 0)
    min_conf = config.get("assert_min_confidence", 0.0)
    require_verified = config.get("assert_require_verified", False)

    if min_count > 0 and len(detections) < min_count:
        return f"assertion: detection count {len(detections)} < {min_count}"
    if require_verified:
        verified = [d for d in detections if d.get("verified")]
        if len(verified) < min_count:
            return f"assertion: verified count {len(verified)} < {min_count}"
    if min_conf > 0:
        for d in detections:
            if d.get("confidence", 1.0) < min_conf:
                return f"assertion: confidence {d.get('confidence')} < {min_conf} for {d.get('label', '?')}"
    return None


async def verify_handler(context: dict, input_data: dict, node_config: dict) -> dict:
    threshold = node_config.get("verify_threshold", 0.5)
    margin = node_config.get("verify_margin", 0.3)
    upper = threshold + margin
    max_retries = node_config.get("verify_max_retries", 0)

    detections = input_data.get("detections", [])
    frame_b64 = context.get("frame", "")
    if not frame_b64 or not detections:
        return {"detections": list(detections), "verification_count": 0, "assertion_passed": True}

    frame, raw = _decode_frame(frame_b64)
    if frame is None:
        return {"detections": detections, "verification_count": 0, "error": "decode_failed"}

    client = _get_verify_client()
    cache = await _get_result_cache()
    hasher = _get_verify_hasher()
    frame_hash = hasher.compute(raw)
    camera_id = context.get("camera_id", "")

    async def _do_verify():
        tasks = []
        verified_detections = []
        v_count = 0

        for det in detections:
            conf = det.get("confidence", 0)
            if threshold <= conf < upper:
                cache_key = f"verify:{det.get('label', '')}"
                cached = None
                if cache:
                    try:
                        cached = await cache.get(camera_id, frame_hash, cache_key)
                    except Exception:
                        pass
                if cached:
                    det["verified"] = cached.result.get("verified", False)
                    det["verification_reason"] = cached.result.get("reason", "")
                    det["verification_cache_hit"] = True
                else:
                    tasks.append(_verify_one_detection(client, cache, frame, det, frame_hash, cache_key, camera_id))
                v_count += 1
            else:
                det["verified"] = True
            verified_detections.append(det)

        if tasks:
            await asyncio.gather(*tasks)

        return {
            "detections": verified_detections,
            "verification_count": v_count,
        }

    result = await _run_with_retry(context, input_data, node_config, max_retries, _do_verify)
    assertion_error = _check_assertions(result.get("detections", []), node_config)
    if assertion_error:
        logger.warning("Verification assertion failed: %s", assertion_error)
        result["assertion_error"] = assertion_error
        result["assertion_passed"] = False
    else:
        result["assertion_passed"] = True
    return result


async def _run_with_retry(context, input_data, node_config, max_retries, verify_fn):
    if max_retries <= 0:
        return await verify_fn() if callable(verify_fn) else verify_fn

    async def _attempt():
        return await verify_fn() if callable(verify_fn) else verify_fn

    try:
        return await retry_with_backoff(
            _attempt,
            max_retries=max_retries,
            base_delay=0.5,
            retryable_exceptions=(Exception,),
        )
    except Exception as e:
        logger.error("Verification retries exhausted: %s", e)
        return {
            "detections": input_data.get("detections", []),
            "verification_count": 0,
            "error": f"retries exhausted: {e}",
        }
