import logging
import time
from pathlib import Path
from typing import Any

import numpy as np

from src.models.inference import ModelAdapter
from src.models.registry import ModelSpec

try:
    import onnxruntime
except ImportError:
    onnxruntime = None

logger = logging.getLogger(__name__)

COCO_CLASSES = [
    "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train",
    "truck", "boat", "traffic light", "fire hydrant", "stop sign",
    "parking meter", "bench", "bird", "cat", "dog", "horse", "sheep", "cow",
    "elephant", "bear", "zebra", "giraffe", "backpack", "umbrella", "handbag",
    "tie", "suitcase", "frisbee", "skis", "snowboard", "sports ball", "kite",
    "baseball bat", "baseball glove", "skateboard", "surfboard",
    "tennis racket", "bottle", "wine glass", "cup", "fork", "knife", "spoon",
    "bowl", "banana", "apple", "sandwich", "orange", "broccoli", "carrot",
    "hot dog", "pizza", "donut", "cake", "chair", "couch", "potted plant",
    "bed", "dining table", "toilet", "tv", "laptop", "mouse", "remote",
    "keyboard", "cell phone", "microwave", "oven", "toaster", "sink",
    "refrigerator", "book", "clock", "vase", "scissors", "teddy bear",
    "hair drier", "toothbrush",
]


class YOLOv8Adapter(ModelAdapter):
    def __init__(self, model_dir: str = "models") -> None:
        self.model_dir = Path(model_dir)
        self._sessions: dict[str, Any] = {}

    def _load_session(self, model_id: str) -> Any:
        if model_id in self._sessions:
            return self._sessions[model_id]
        model_path = self.model_dir / f"{model_id}.onnx"
        if not model_path.exists():
            logger.warning("ONNX model not found: %s", model_path)
            return None
        if onnxruntime is None:
            logger.warning("onnxruntime not installed")
            return None
        session = onnxruntime.InferenceSession(str(model_path))
        self._sessions[model_id] = session
        return session

    def _preprocess(self, image: np.ndarray) -> tuple[np.ndarray, float, int, int]:
        import cv2
        input_size = 640
        h, w = image.shape[:2]
        scale = min(input_size / h, input_size / w)
        nh, nw = int(h * scale), int(w * scale)
        resized = cv2.resize(image, (nw, nh), interpolation=cv2.INTER_LINEAR)

        dw = input_size - nw
        dh = input_size - nh
        top, bottom = dh // 2, dh - dh // 2
        left, right = dw // 2, dw - dw // 2
        padded = cv2.copyMakeBorder(
            resized, top, bottom, left, right,
            cv2.BORDER_CONSTANT, value=(114, 114, 114),
        )
        blob = padded.transpose(2, 0, 1).astype(np.float32) / 255.0
        blob = np.expand_dims(blob, axis=0)
        return blob, scale, left, top

    def _nms(
        self, boxes: np.ndarray, scores: np.ndarray, iou_threshold: float = 0.45
    ) -> list[int]:
        x1 = boxes[:, 0]
        y1 = boxes[:, 1]
        x2 = boxes[:, 2]
        y2 = boxes[:, 3]
        areas = (x2 - x1) * (y2 - y1)
        order = scores.argsort()[::-1]
        keep = []
        while order.size > 0:
            i = order[0]
            keep.append(i)
            xx1 = np.maximum(x1[i], x1[order[1:]])
            yy1 = np.maximum(y1[i], y1[order[1:]])
            xx2 = np.minimum(x2[i], x2[order[1:]])
            yy2 = np.minimum(y2[i], y2[order[1:]])
            inter = np.maximum(0, xx2 - xx1) * np.maximum(0, yy2 - yy1)
            iou = inter / (areas[i] + areas[order[1:]] - inter)
            inds = np.where(iou <= iou_threshold)[0]
            order = order[inds + 1]
        return keep

    def _postprocess(
        self, outputs: list[np.ndarray], scale: float, pad_left: int, pad_top: int,
        conf_threshold: float = 0.25,
    ) -> list[dict]:
        predictions = np.squeeze(outputs[0])
        if predictions.ndim == 1:
            return []

        all_boxes, all_scores, all_class_ids = [], [], []

        for pred in predictions.T:
            scores = pred[4:]
            class_id = int(np.argmax(scores))
            confidence = float(scores[class_id])
            if confidence < conf_threshold:
                continue

            cx, cy, w, h = pred[:4]
            cx = (cx - pad_left) / scale
            cy = (cy - pad_top) / scale
            w = w / scale
            h = h / scale
            x1 = int(max(0, cx - w / 2))
            y1 = int(max(0, cy - h / 2))
            x2 = int(cx + w / 2)
            y2 = int(cy + h / 2)

            all_boxes.append([x1, y1, x2, y2])
            all_scores.append(confidence)
            all_class_ids.append(class_id)

        if not all_boxes:
            return []

        boxes = np.array(all_boxes)
        scores = np.array(all_scores)
        keep = self._nms(boxes, scores)

        detections = []
        for idx in keep:
            class_id = all_class_ids[idx]
            label = COCO_CLASSES[class_id] if class_id < len(COCO_CLASSES) else f"class_{class_id}"
            detections.append({
                "bbox": [int(v) for v in boxes[idx].tolist()],
                "label": label,
                "class_id": class_id,
                "confidence": round(float(scores[idx]), 4),
            })
        return detections

    async def predict(self, spec: ModelSpec, input_data: Any) -> dict:
        session = self._load_session(spec.model_id)
        if session is None:
            return {"detections": [], "stub": True, "model_loaded": False}

        image = input_data.get("image")
        if image is None:
            logger.warning("No image provided for %s", spec.model_id)
            return {"detections": [], "error": "no_image"}

        start = time.monotonic()
        blob, scale, pad_left, pad_top = self._preprocess(image)
        inputs = [o.name for o in session.get_inputs()]
        outputs = session.run(None, {inputs[0]: blob})
        detections = self._postprocess(outputs, scale, pad_left, pad_top)
        elapsed_ms = (time.monotonic() - start) * 1000

        return {
            "detections": detections,
            "count": len(detections),
            "model_loaded": True,
            "inference_ms": round(elapsed_ms, 1),
        }
