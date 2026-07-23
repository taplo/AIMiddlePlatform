#!/usr/bin/env python3
"""Download all model weights required by the platform.

Usage:
    python -m scripts.download_models              # download all missing models
    python -m scripts.download_models --check       # check which models are missing
    python -m scripts.download_models --force       # re-download all models
"""

import argparse
import sys
import urllib.request
from pathlib import Path

MODEL_DIR = Path(__file__).resolve().parent.parent / "models"

MODELS: dict[str, dict] = {
    "yolov8n": {
        "url": "https://github.com/ultralytics/assets/releases/download/v8.2.0/yolov8n.onnx",
        "filename": "yolov8n.onnx",
        "description": "YOLOv8n 目标检测（轻量级）",
    },
    "yolov8s": {
        "url": "https://github.com/ultralytics/assets/releases/download/v8.2.0/yolov8s.onnx",
        "filename": "yolov8s.onnx",
        "description": "YOLOv8s 目标检测（标准版）",
    },
    "object_detection": {
        "url": "https://github.com/ultralytics/assets/releases/download/v8.2.0/yolov8m.onnx",
        "filename": "object_detection.onnx",
        "description": "YOLOv8m 目标检测（精度版，即 object_detection）",
    },
}

_MISSING_OK = {
    "face_recognition",
    "license_plate",
    "vehicle_detection",
    "ocr",
    "person_reid",
    "yolo_world",
}


def _progress(block_count: int, block_size: int, total_size: int) -> None:
    downloaded = block_count * block_size
    if total_size > 0:
        pct = min(100, downloaded * 100 // total_size)
        bar = "#" * (pct // 5) + "-" * (20 - pct // 5)
        sys.stdout.write(f"\r  [{bar}] {pct}% ({downloaded / 1e6:.1f} / {total_size / 1e6:.1f} MB)")
    else:
        sys.stdout.write(f"\r  Downloaded {downloaded / 1e6:.1f} MB")
    sys.stdout.flush()


def check_models() -> dict[str, bool]:
    results: dict[str, bool] = {}
    for model_id, info in MODELS.items():
        path = MODEL_DIR / info["filename"]
        results[model_id] = path.exists()
    return results


def download_model(model_id: str, force: bool = False) -> bool:
    info = MODELS.get(model_id)
    if info is None:
        print(f"  Unknown model: {model_id}")
        return False

    dest = MODEL_DIR / info["filename"]
    if dest.exists() and not force:
        print(f"  {model_id}: already exists, skipping")
        return True

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    url = info["url"]
    print(f"  Downloading {model_id} ({info['description']})...")
    print(f"    from: {url}")
    try:
        urllib.request.urlretrieve(url, str(dest), _progress)
        print()
        size = dest.stat().st_size
        print(f"    done: {size / 1e6:.1f} MB")
        return True
    except Exception as e:
        print(f"    FAILED: {e}")
        if dest.exists():
            dest.unlink()
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Download model weights")
    parser.add_argument("--check", action="store_true", help="Check which models are missing")
    parser.add_argument("--force", action="store_true", help="Re-download existing models")
    args = parser.parse_args()

    if args.check:
        print("Checking model status:")
        results = check_models()
        for model_id, ok in results.items():
            status = "OK" if ok else "MISSING"
            print(f"  {model_id:20s} [{status}]")
        missing = [m for m, ok in results.items() if not ok]
        if missing:
            print(f"\n{len(missing)} model(s) missing. Run without --check to download.")
        else:
            print("\nAll models present.")
        return

    print("Downloading models to:", MODEL_DIR)
    results = check_models()
    success = 0
    failed = 0
    for model_id in MODELS:
        if results.get(model_id) and not args.force:
            success += 1
            continue
        if download_model(model_id, force=args.force):
            success += 1
        else:
            failed += 1

    print(f"\nSummary: {success} OK, {failed} failed")
    if _MISSING_OK:
        print("\nNote: The following models require manual download (no public URL):")
        for m in sorted(_MISSING_OK):
            print(f"  - {m}")
        print(f"  Place .onnx files in: {MODEL_DIR}")

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
