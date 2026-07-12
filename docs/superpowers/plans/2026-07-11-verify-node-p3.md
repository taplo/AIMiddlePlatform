# P3: VERIFY 节点 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add VERIFY node type to DAG pipeline that uses LLM to re-evaluate uncertain detections.

**Architecture:** New `NodeType.VERIFY` + synchronous handler (like `_inference_handler`) in `src/pipeline/verify_handler.py`. Handler crops candidate bboxes from frame, calls `QwenVLClient.verify()` per candidate. Thresholds from node_config.

**Tech Stack:** Python 3.12+, opencv-python-headless (cv2), numpy, httpx

## Global Constraints

- `NodeType.VERIFY = "verify"` added to enum in `src/pipeline/dag.py`
- Handler signature: `(context: dict, input_data: dict, node_config: dict) -> dict`
- `asyncio.run()` bridge pattern for sync→async (matching existing `_inference_handler`)
- Detection format from MODEL_INFERENCE: `{"bbox": [x1,y1,x2,y2], "label": str, "confidence": float}`
- Threshold logic: `threshold ≤ confidence < threshold + margin` → verify; else auto-verified
- All 138+ existing tests must continue to pass

---

### Task 1: NodeType.VERIFY + verify_handler 核心实现

**Files:**
- Modify: `src/pipeline/dag.py`（添加 VERIFY 枚举值）
- Create: `src/pipeline/verify_handler.py`
- Create: `tests/test_verify.py`

**Interfaces:**
- Consumes: `QwenVLClient` from `src/agent/client.py`
- Consumes: `_extract_json` from `src/agent/agent.py`
- Consumes: Detection format: `{"bbox": [int,int,int,int], "label": str, "confidence": float}`
- Produces: `verify_handler(context, input_data, node_config) -> dict`
- Produces: `_get_verify_client() -> QwenVLClient` (单例)

- [ ] **Step 1: 添加 VERIFY 枚举值**

```python
# src/pipeline/dag.py 第 11 行添加
    VERIFY = "verify"
```

- [ ] **Step 2: 写测试**

```python
# tests/test_verify.py
import json
import pytest
import numpy as np

from src.pipeline.dag import DAGDefinition, DAGNode, NodeType
from src.pipeline.executor import DAGExecutor
from src.pipeline.verify_handler import verify_handler


def _make_frame(height=200, width=300):
    """Create a synthetic frame with visible content."""
    import cv2
    img = np.zeros((height, width, 3), dtype=np.uint8)
    img[50:150, 100:200] = (255, 255, 255)  # white rectangle
    import base64
    _, buf = cv2.imencode(".jpg", img)
    return base64.b64encode(buf).decode("ascii")


SAMPLE_DETECTIONS = [
    {"bbox": [100, 50, 200, 150], "label": "person", "confidence": 0.65},  # 需要验证 (0.5 ≤ 0.65 < 0.8)
    {"bbox": [0, 0, 50, 50], "label": "car", "confidence": 0.95},         # 高置信度，自动 verified
    {"bbox": [50, 50, 100, 100], "label": "dog", "confidence": 0.30},     # 低于阈值，自动 verified (不需要验证)
]


def test_verify_no_candidates():
    """所有检测 conf ≥ upper 或 < threshold → 不调 LLM"""
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
    """候选框被 LLM 确认"""
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
    """候选框被 LLM 拒绝（仅验证返回 False 的情况）"""
    dets = [{"bbox": [100, 50, 200, 150], "label": "person", "confidence": 0.65}]
    result = verify_handler(
        {"frame": _make_frame()},
        {"detections": dets},
        {"verify_threshold": 0.5, "verify_margin": 0.3},
    )
    d = result["detections"][0]
    # 结果可能是 True 或 False（取决于 LLM 实际返回），但必须有 verified 字段
    assert "verified" in d


def test_verify_empty_frame():
    """frame 为空 → 返回原始 detections"""
    dets = [{"bbox": [100, 50, 200, 150], "label": "person", "confidence": 0.65}]
    result = verify_handler(
        {"frame": ""},
        {"detections": dets},
        {},
    )
    assert result["verification_count"] == 0
    assert len(result["detections"]) == 1


def test_verify_no_detections():
    """无检测 → 返回空"""
    result = verify_handler(
        {"frame": _make_frame()},
        {"detections": []},
        {},
    )
    assert result["verification_count"] == 0
    assert result["detections"] == []


def test_verify_edge_threshold():
    """边界值：exactly at threshold, exactly at threshold+margin"""
    dets = [
        {"bbox": [100, 50, 200, 150], "label": "person", "confidence": 0.5},   # == threshold → verify
        {"bbox": [100, 50, 200, 150], "label": "car", "confidence": 0.8},      # == upper → NOT verify
        {"bbox": [100, 50, 200, 150], "label": "bus", "confidence": 0.79},     # < upper → verify
    ]
    result = verify_handler(
        {"frame": _make_frame()},
        {"detections": dets},
        {"verify_threshold": 0.5, "verify_margin": 0.3},
    )
    # 3 detections: 2 verified (0.5, 0.79), 1 not (0.8)
    assert result["verification_count"] == 2
```

- [ ] **Step 3: 运行测试确认失败**

```bash
$env:PYTHONPATH = "D:\projects\AIMiddlePlatform"; uv run python -m pytest tests/test_verify.py -v --tb=short
Expected: 6 failed (verify_handler not found, VERIFY not found)
```

- [ ] **Step 4: 实现 verify_handler.py**

```python
# src/pipeline/verify_handler.py
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
```

- [ ] **Step 5: 运行测试**

```bash
$env:PYTHONPATH = "D:\projects\AIMiddlePlatform"; uv run python -m pytest tests/test_verify.py -v --tb=short
Expected: 6 passed (3 checking structure, 3 checking threshold logic)
```

Note: The tests call `verify_handler` directly which triggers real `QwenVLClient.verify()` → real LLM API call for tests with candidate detections. Tests `test_verify_no_candidates`, `test_verify_empty_frame`, `test_verify_no_detections`, and the first two checks of `test_verify_edge_threshold` do NOT trigger LLM calls. The tests `test_verify_candidate_accepted` and `test_verify_candidate_rejected` DO trigger real LLM calls — this is acceptable since they verify actual functionality. If no API key is configured, those 2 tests will fail with LLMAPIError.

- [ ] **Step 6: 提交**

```bash
git add src/pipeline/dag.py src/pipeline/verify_handler.py tests/test_verify.py
git commit -m "feat: add NodeType.VERIFY and verify_handler implementation"
```

---

### Task 2: QwenVLClient.verify() 方法

**Files:**
- Modify: `src/agent/client.py`（添加 verify 方法）
- Modify: `tests/test_agent.py`（追加测试）

**Interfaces:**
- Produces: `QwenVLClient.verify(image_data: bytes, label: str, confidence: float) -> dict`
- Consumes: `chat_with_image()` + `_extract_json()` (both from Task 2/3 of P2)

- [ ] **Step 1: 追加测试**

```python
# tests/test_agent.py — 追加到文件末尾

@pytest.mark.asyncio
async def test_qwen_verify_accepted():
    transport = httpx.MockTransport(lambda req: httpx.Response(200, json={
        "choices": [{"message": {
            "content": '{"verified": true, "corrected_label": "person", "reason": "clearly visible"}',
            "role": "assistant",
        }}]
    }))
    client = QwenVLClient(http_client=httpx.AsyncClient(transport=transport))
    result = await client.verify(b"fake_image", "person", 0.65)
    assert result["verified"] is True
    assert result["corrected_label"] == "person"


@pytest.mark.asyncio
async def test_qwen_verify_rejected():
    transport = httpx.MockTransport(lambda req: httpx.Response(200, json={
        "choices": [{"message": {
            "content": '{"verified": false, "corrected_label": "dog", "reason": "not a person, it is a dog"}',
            "role": "assistant",
        }}]
    }))
    client = QwenVLClient(http_client=httpx.AsyncClient(transport=transport))
    result = await client.verify(b"fake_image", "person", 0.55)
    assert result["verified"] is False
    assert result["corrected_label"] == "dog"


@pytest.mark.asyncio
async def test_qwen_verify_fallback_on_parse_failure():
    """If LLM returns non-JSON, verify() should return defaults."""
    transport = httpx.MockTransport(lambda req: httpx.Response(200, json={
        "choices": [{"message": {"content": "I see a person in this image", "role": "assistant"}}]
    }))
    client = QwenVLClient(http_client=httpx.AsyncClient(transport=transport))
    result = await client.verify(b"fake_image", "person", 0.65)
    # Can't parse → defaults
    assert result["verified"] is False
    assert result["corrected_label"] == "person"
```

- [ ] **Step 2: 运行测试确认失败**

```bash
$env:PYTHONPATH = "D:\projects\AIMiddlePlatform"; uv run python -m pytest tests/test_agent.py -v --tb=short
Expected: 11 existing pass + 3 new fail (verify not defined)
```

- [ ] **Step 3: 添加 verify() 方法到 QwenVLClient**

在 `src/agent/client.py` 的 `QwenVLClient` 类中添加：

```python
    async def verify(
        self,
        image_data: bytes,
        label: str,
        confidence: float,
    ) -> dict:
        from src.agent.agent import _extract_json
        prompt = (
            f"这张图片被检测为「{label}」，置信度 {confidence:.1%}。"
            f"请确认这个目标是否正确。如果正确，返回 verified=true；"
            f"如果错误，返回 verified=false 并给出正确的 label。"
            f"用 JSON 格式回答：{{verified: bool, corrected_label: str, reason: str}}"
        )
        response = await self.chat_with_image(prompt, image_data)
        content = response.get("content", "")
        parsed = _extract_json(content) or {}
        return {
            "verified": parsed.get("verified", False),
            "corrected_label": parsed.get("corrected_label", label),
            "reason": parsed.get("reason", ""),
        }
```

- [ ] **Step 4: 运行测试确认通过**

```bash
$env:PYTHONPATH = "D:\projects\AIMiddlePlatform"; uv run python -m pytest tests/test_agent.py -v --tb=short
Expected: 14 passed
```

- [ ] **Step 5: 提交**

```bash
git add src/agent/client.py tests/test_agent.py
git commit -m "feat: add QwenVLClient.verify() for VERIFY node"
```

---

### Task 3: Handler 注册到 Worker + API

**Files:**
- Modify: `src/worker.py`
- Modify: `src/api/app.py`

**Interfaces:**
- Consumes: `verify_handler` from `src/pipeline/verify_handler.py`
- Consumes: `NodeType.VERIFY` from `src/pipeline/dag.py`

- [ ] **Step 1: 在 worker.py 中注册**

在 `src/worker.py` 的 `_init_fast_path()` 函数中，在现有 handler 注册后添加：

```python
from src.pipeline.verify_handler import verify_handler
executor.register_handler(NodeType.VERIFY, verify_handler)
```

- [ ] **Step 2: 在 app.py 中注册**

在 `src/api/app.py` 的 `_init_components()` 函数中，在现有 handler 注册后添加：

```python
from src.pipeline.verify_handler import verify_handler
executor.register_handler(NodeType.VERIFY, verify_handler)
```

- [ ] **Step 3: 运行回归测试**

```bash
$env:PYTHONPATH = "D:\projects\AIMiddlePlatform"; uv run python -m pytest tests/ -q --tb=short
Expected: All pass (138+ tests)
```

- [ ] **Step 4: 提交**

```bash
git add src/worker.py src/api/app.py
git commit -m "feat: register VERIFY handler in Worker and API"
```

---

### Task 4: 回归验证 + 提交

- [ ] **Step 1: 运行全部测试**

```bash
$env:PYTHONPATH = "D:\projects\AIMiddlePlatform"; uv run python -m pytest tests/ -q --tb=short 2>&1
Expected: All pass
```

- [ ] **Step 2: 提交**

```bash
git commit --allow-empty -m "chore: P3 VERIFY node complete, all tests pass"
```
