from src.models.registry import ModelRegistry, ModelSpec, ModelStatus


def register_default_models(registry: ModelRegistry) -> None:
    models = [
        ModelSpec(
            model_id="object_detection",
            name="目标检测",
            description="通用目标检测，支持人、车、物等常见目标的检测与定位",
            version="1.0.0",
            backend="onnx",
            input_schema={"type": "image", "format": "np_array"},
            output_schema={"type": "detections", "fields": ["bbox", "label", "confidence"]},
            cost_estimate="low",
            tags=["detection", "general"],
        ),
        ModelSpec(
            model_id="face_recognition",
            name="人脸识别",
            description="人脸检测、特征提取与比对",
            version="1.0.0",
            backend="onnx",
            input_schema={"type": "image", "format": "np_array"},
            output_schema={"type": "faces", "fields": ["bbox", "embedding", "identity"]},
            cost_estimate="medium",
            tags=["face", "recognition"],
        ),
        ModelSpec(
            model_id="license_plate",
            name="车牌识别",
            description="车牌检测与光学字符识别",
            version="1.0.0",
            backend="onnx",
            input_schema={"type": "image", "format": "np_array"},
            output_schema={"type": "plate", "fields": ["plate_number", "color", "confidence"]},
            cost_estimate="low",
            tags=["plate", "ocr"],
        ),
        ModelSpec(
            model_id="vehicle_detection",
            name="车辆检测",
            description="车辆类型检测（轿车/SUV/卡车/巴士等）",
            version="1.0.0",
            backend="onnx",
            input_schema={"type": "image", "format": "np_array"},
            output_schema={"type": "vehicles", "fields": ["bbox", "type", "confidence"]},
            cost_estimate="low",
            tags=["vehicle", "detection"],
        ),
        ModelSpec(
            model_id="ocr",
            name="文字识别 OCR",
            description="自然场景文字检测与识别",
            version="1.0.0",
            backend="onnx",
            input_schema={"type": "image", "format": "np_array"},
            output_schema={"type": "texts", "fields": ["text", "bbox", "confidence"]},
            cost_estimate="medium",
            tags=["ocr", "text"],
        ),
        ModelSpec(
            model_id="person_reid",
            name="行人重识别 ReID",
            description="跨摄像头行人特征提取与匹配",
            version="1.0.0",
            backend="onnx",
            input_schema={"type": "image", "format": "np_array"},
            output_schema={"type": "features", "fields": ["embedding", "camera_id"]},
            cost_estimate="medium",
            tags=["reid", "person"],
        ),
    ]

    for m in models:
        registry.register(m)
