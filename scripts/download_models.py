#!/usr/bin/env python3
"""Download open-source ONNX models for development and testing.

Downloads:
  - yolov8s.onnx  — YOLOv8 small (COCO, 80 classes: person, vehicles, etc.)
  - yolov8n-seg.onnx  — YOLOv8 nano segmentation (COCO)
  - fire_smoke.onnx  — Fire & smoke detection (if available)
"""

import os
import urllib.request
from pathlib import Path

MODELS_DIR = Path(__file__).resolve().parent.parent / "models"
PROXY = "http://192.168.3.208:8787"

# Proxy handler
proxy_support = urllib.request.ProxyHandler({"http": PROXY, "https": PROXY})
opener = urllib.request.build_opener(proxy_support)
urllib.request.install_opener(opener)

MODELS = {
    "yolov8s.onnx": {
        "url": "https://github.com/ultralytics/assets/releases/download/v8.4.0/yolov8s.onnx",
        "desc": "YOLOv8 small, COCO 80-class detection (person, car, bus, truck, etc.)",
        "size_mb": 22.5,
    },
    "yolov8n-seg.onnx": {
        "url": "https://github.com/ultralytics/assets/releases/download/v8.4.0/yolov8n-seg.onnx",
        "desc": "YOLOv8 nano segmentation, COCO 80-class instance segmentation",
        "size_mb": 6.8,
    },
}

FIRE_CANDIDATES = [
    # HuggingFace direct download (may or may not be accessible)
    ("fire_smoke.onnx", "https://huggingface.co/prithivMLmods/Fire-Detection-Engine-ONNX/resolve/main/onnx/model.onnx"),
    # Alternative: ultralytics-based fire model URLs (checking if pre-exported exists)
]

def download(url, dest, label):
    print(f"Downloading {label}...")
    print(f"  URL: {url}")
    print(f"  -> {dest}")
    try:
        urllib.request.urlretrieve(url, dest)
        size_mb = os.path.getsize(dest) / (1024 * 1024)
        print(f"  Done ({size_mb:.1f} MB)")
        return True
    except Exception as e:
        print(f"  FAILED: {e}")
        if dest.exists():
            dest.unlink()
        return False

def main():
    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    # Download standard YOLO models
    for filename, info in MODELS.items():
        dest = MODELS_DIR / filename
        if dest.exists():
            print(f"Skipping {filename} (already exists, {dest.stat().st_size / 1024 / 1024:.1f} MB)")
            continue
        download(info["url"], dest, f"{filename} ({info['desc']})")

    # Try fire/smoke models
    for filename, url in FIRE_CANDIDATES:
        dest = MODELS_DIR / filename
        if dest.exists():
            print(f"Skipping {filename} (already exists)")
            continue
        success = download(url, dest, filename)
        if success:
            break
        print("  Trying next fire model source...")

    # Summary
    print("\n=== Models summary ===")
    for f in sorted(MODELS_DIR.glob("*.onnx")):
        print(f"  {f.name:30s} {f.stat().st_size / 1024 / 1024:.1f} MB")

if __name__ == "__main__":
    main()
