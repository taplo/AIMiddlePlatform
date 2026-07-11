# P3: VERIFY 节点 — 设计文档

## 1. 目标

在 DAG 管线中增加 VERIFY 节点类型，对小模型检测结果中置信度处于阈值边缘的 detection 进行 LLM 二次确认，降低误报率。

## 2. 范围

### 包含
- `NodeType.VERIFY` 枚举值
- `QwenVLClient.verify()` 方法（逐目标验证）
- VERIFY handler（裁剪 + LLM 调用 + 结果标注）
- Handler 在 Worker 和 API 中的注册
- 参数化阈值：`verify_threshold` + `verify_margin`
- 全部现有测试继续通过

### 不包含
- 批量验证
- VERIFY 结果写 Alert 表（P5）
- 前端阈值配置 UI（P5+）
- 视频帧缓存（P4）

## 3. 架构

```
MODEL_INFERENCE 输出
  { detections: [{bbox, label, confidence}, ...] }
        │
        ▼
VERIFY handler
        │
  1. 从 context 取 frame (base64)
  2. 解码 → 裁剪候选 bbox → 编码为 JPEG
  3. 对每个候选调用 QwenVLClient.verify()
  4. 标注 verified / corrected_label
        │
        ▼
  { detections: [{..., verified: true, verification_confidence: 0.9}],
    verification_count: N }
```

## 4. 组件设计

### 4.1 NodeType 枚举

```python
class NodeType(Enum):
    MODEL_INFERENCE = "model_inference"
    CONDITION = "condition"
    AGGREGATE = "aggregate"
    OUTPUT = "output"
    VERIFY = "verify"  # 新增
```

### 4.2 QwenVLClient.verify()

```python
async def verify(
    self,
    image_data: bytes,
    label: str,
    confidence: float,
) -> dict:
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

复用 `chat_with_image` 和 `_extract_json`（P2 已实现）。

### 4.3 VERIFY Handler

新文件 `src/pipeline/verify_handler.py`：

```python
import base64
import cv2
import numpy as np

def verify_handler(context: dict, input_data: dict, node_config: dict) -> dict:
    """
    Synchronous handler (runs in asyncio.to_thread).
    - context: {"frame": base64_str}
    - input_data: {"detections": [...]} from previous MODEL_INFERENCE node
    - node_config: {"verify_threshold": 0.5, "verify_margin": 0.3}
    """
    threshold = node_config.get("verify_threshold", 0.5)
    margin = node_config.get("verify_margin", 0.3)
    upper = threshold + margin

    detections = input_data.get("detections", [])
    frame_b64 = context.get("frame", "")
    if not frame_b64 or not detections:
        return {"detections": detections, "verification_count": 0}

    # Decode full frame
    raw = base64.b64decode(frame_b64)
    arr = np.frombuffer(raw, dtype=np.uint8)
    frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if frame is None:
        return {"detections": detections, "verification_count": 0, "error": "decode_failed"}

    import asyncio
    client = _get_verify_client()
    verified_detections = []
    v_count = 0

    for det in detections:
        conf = det.get("confidence", 0)
        if threshold <= conf < upper:
            # Crop
            x1, y1, x2, y2 = det.get("bbox", [0, 0, 0, 0])
            crop = frame[y1:y2, x1:x2]
            if crop.size == 0:
                det["verified"] = False
                det["verification_error"] = "empty_crop"
                verified_detections.append(det)
                continue
            _, buf = cv2.imencode(".jpg", crop, [cv2.IMWRITE_JPEG_QUALITY, 85])
            crop_bytes = buf.tobytes()
            # Call LLM
            result = asyncio.run(client.verify(crop_bytes, det.get("label", ""), conf))
            det["verified"] = result.get("verified", False)
            if result.get("corrected_label"):
                det["corrected_label"] = result["corrected_label"]
            det["verification_reason"] = result.get("reason", "")
            v_count += 1
        else:
            det["verified"] = True  # High-confidence, auto-verified
        verified_detections.append(det)

    return {
        "detections": verified_detections,
        "verification_count": v_count,
    }
```

### 4.4 注册 Handler

Worker 和 API 的 _init_fast_path / _init_components 中：

```python
from src.pipeline.verify_handler import verify_handler
executor.register_handler(NodeType.VERIFY, verify_handler)
```

同时 executor 需要导入 NodeType.VERIFY — NodeType 已包含 VERIFY。

### 4.5 verify client 单例

VERIFY handler 需要访问 QwenVLClient。为避免在同步 handler 中每次都创建新 client，用模块级变量：

```python
# src/pipeline/verify_handler.py
_verify_client = None

def _get_verify_client():
    global _verify_client
    if _verify_client is None:
        from src.agent.client import QwenVLClient
        _verify_client = QwenVLClient()
    return _verify_client
```

## 5. 测试

| 测试 | 描述 |
|------|------|
| `test_verify_no_candidates` | 所有检测 conf ≥ upper → 不调 LLM |
| `test_verify_candidate_accepted` | 一个候选框，LLM 确认 |
| `test_verify_candidate_rejected` | 一个候选框，LLM 拒绝 |
| `test_verify_empty_frame` | frame 为空 → 返回原始 detections |
| `test_verify_no_detections` | 无检测 → 返回空 |

测试策略：mock QwenVLClient.verify() 直接返回预定结果，不需要 HTTP。

## 6. 任务分解

| # | 任务 | 文件 | 测试 |
|---|------|------|------|
| 1 | NodeType.VERIFY + verify_handler 实现 | `src/pipeline/dag.py`, `src/pipeline/verify_handler.py` | `tests/test_verify.py` |
| 2 | QwenVLClient.verify() 方法 | `src/agent/client.py` | 追加到 `tests/test_agent.py` |
| 3 | Handler 注册到 Worker + API | `src/worker.py`, `src/api/app.py` | 回归测试 |
| 4 | 回归验证 | — | 全量 |

## 7. 风险

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| LLM 延迟导致 DAG 执行超时 | 中 | 高 | timeout 控制；VERIFY handler 可配置超时 |
| 裁剪区域过小无法识别 | 低 | 中 | 最小裁剪尺寸限制 |
| Qwen-VL API 不可用 | 中 | 中 | skip_verify 配置项 |
