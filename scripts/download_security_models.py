"""Download pre-trained ONNX models for security/surveillance CV tasks."""

import os
import sys
import urllib.request

MODELS = {
    "yolov8n.onnx": {
        "url": "https://github.com/ultralytics/assets/releases/download/v8.2.0/yolov8n.onnx",
        "desc": "YOLOv8n nano — general object detection (COCO, 80 classes)",
    },
    "yolov8s.onnx": {
        "url": "https://github.com/ultralytics/assets/releases/download/v8.2.0/yolov8s.onnx",
        "desc": "YOLOv8s small — more accurate general object detection",
    },
    "yolov8n-seg.onnx": {
        "url": "https://github.com/ultralytics/assets/releases/download/v8.2.0/yolov8n-seg.onnx",
        "desc": "YOLOv8n-seg — instance segmentation",
    },
    "yolov8n-face.onnx": {
        "url": "https://github.com/yakhyo/yolov8-face-onnx-inference/releases/download/weights/yolov8n-face.onnx",
        "desc": "YOLOv8n-face — face detection (WIDERFace, 5 landmarks)",
    },
    "w600k_mbf.onnx": {
        "url": "https://github.com/yakhyo/face-reidentification/releases/download/v0.0.1/w600k_mbf.onnx",
        "desc": "ArcFace MobileFaceNet — face recognition (512-dim embedding)",
    },
}

LFS_SUGGEST = """Models > 100 MB should use Git LFS:
  fire_smoke_classifier.onnx (327 MB)
  yolov8s.onnx (43 MB) - borderline, optional"""

dest_dir = os.path.dirname(os.path.abspath(__file__))

if len(sys.argv) > 1:
    selected = [k for k in MODELS if sys.argv[1] in k]
    if not selected:
        names = "\n".join(f"  {k}  ({v['desc']})" for k, v in MODELS.items())
        print(f"Usage: python download_model.py [model_name]\n\nAvailable models:\n{names}")
        sys.exit(1)
else:
    selected = list(MODELS)

for name in selected:
    info = MODELS[name]
    path = os.path.join(dest_dir, name)
    if os.path.exists(path):
        print(f"[SKIP] {name} — already exists ({os.path.getsize(path) / 1e6:.1f} MB)")
        continue
    print(f"[DL]   {name} — {info['desc']}")
    try:
        urllib.request.urlretrieve(info["url"], path)
        size = os.path.getsize(path)
        print(f"[OK]   {name} — {size / 1e6:.1f} MB")
    except Exception as e:
        print(f"[FAIL] {name} — {e}", file=sys.stderr)
