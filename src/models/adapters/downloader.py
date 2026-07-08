import logging
from pathlib import Path

logger = logging.getLogger(__name__)

MODEL_URLS: dict[str, str] = {
    "yolov8n": "https://github.com/ultralytics/assets/releases/download/v8.2.0/yolov8n.onnx",
    "yolov8s": "https://github.com/ultralytics/assets/releases/download/v8.2.0/yolov8s.onnx",
    "yolov8m": "https://github.com/ultralytics/assets/releases/download/v8.2.0/yolov8m.onnx",
}


def ensure_model(model_id: str, model_dir: str = "models") -> Path:
    model_path = Path(model_dir) / f"{model_id}.onnx"
    if model_path.exists():
        logger.info("Model already exists: %s", model_path)
        return model_path

    url = MODEL_URLS.get(model_id)
    if url is None:
        raise ValueError(f"No download URL for model: {model_id}")

    model_path.parent.mkdir(parents=True, exist_ok=True)
    import urllib.request
    logger.info("Downloading model %s from %s ...", model_id, url)
    urllib.request.urlretrieve(url, str(model_path))
    logger.info("Downloaded: %s (%.1f MB)", model_path, model_path.stat().st_size / 1e6)
    return model_path
