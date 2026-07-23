#!/usr/bin/env python3
"""Standalone model inference server for K8s Deployment.

Each model runs as its own Deployment. This script loads a single model
and exposes it via HTTP for remote inference from the main API/Worker.

Usage:
    python -m src.models.serve_model --model-id object_detection
    python -m src.models.serve_model --model-id yolov8n --port 8501
"""

import argparse
import logging
import os

import numpy as np
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from src.models.adapters.yolo_world_adapter import YOLOWorldAdapter
from src.models.adapters.yolov8_adapter import YOLOv8Adapter
from src.models.inference import InferenceOrchestrator
from src.models.registry import ModelRegistry

logger = logging.getLogger(__name__)

app = FastAPI(title="Model Inference Server")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_orchestrator: InferenceOrchestrator | None = None


@app.on_event("startup")
async def startup():
    global _orchestrator
    model_id = os.environ.get("MODEL_ID", "")
    if not model_id:
        logger.error("MODEL_ID not set")
        return

    model_dir = os.environ.get("MODEL_DIR", "models")
    registry = ModelRegistry()
    from src.models.presets import register_default_models
    register_default_models(registry)

    spec = registry.get(model_id)
    if spec is None:
        logger.error("Model %s not found in registry", model_id)
        return

    orchestrator = InferenceOrchestrator(registry)
    orchestrator.register_adapter("onnx", YOLOv8Adapter(model_dir=model_dir))
    orchestrator.register_adapter("onnx", YOLOWorldAdapter(model_dir=model_dir))
    _orchestrator = orchestrator
    logger.info("Model %s inference server ready", model_id)


@app.get("/health")
async def health():
    return {"ok": True, "model_id": os.environ.get("MODEL_ID", "")}


@app.get("/ready")
async def ready():
    if _orchestrator is None:
        raise HTTPException(503, "Model not loaded")
    return {"ok": True}


@app.post("/predict")
async def predict(body: dict):
    if _orchestrator is None:
        raise HTTPException(503, "Model not loaded")

    model_id = os.environ.get("MODEL_ID", "")
    image_data = body.get("image")
    if image_data is None:
        raise HTTPException(400, "Missing 'image' field")

    import base64

    import cv2
    try:
        raw = base64.b64decode(image_data)
        arr = np.frombuffer(raw, dtype=np.uint8)
        image = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError("Failed to decode image")
    except Exception as e:
        raise HTTPException(400, f"Invalid image: {e}")

    result = await _orchestrator.infer(model_id, {"image": image})
    return {"model_id": model_id, "result": result}


def main():
    parser = argparse.ArgumentParser(description="Model inference server")
    parser.add_argument("--model-id", default=os.environ.get("MODEL_ID", ""), help="Model ID to serve")
    parser.add_argument("--port", type=int, default=int(os.environ.get("INFERENCE_PORT", "8501")), help="HTTP port")
    parser.add_argument("--host", default="0.0.0.0", help="Bind address")
    args = parser.parse_args()

    if not args.model_id:
        print("Error: --model-id is required")
        return 1

    os.environ["MODEL_ID"] = args.model_id
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    logger.info("Starting model server: %s on %s:%d", args.model_id, args.host, args.port)
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    exit(main())
