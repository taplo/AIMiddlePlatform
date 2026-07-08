import logging
from typing import Any

from src.models.inference import InferenceOrchestrator

logger = logging.getLogger(__name__)


class ToolRegistry:
    def __init__(self, orchestrator: InferenceOrchestrator) -> None:
        self.orchestrator = orchestrator
        self._tools: dict[str, dict[str, Any]] = {}

    def register_tool(
        self,
        name: str,
        description: str,
        parameters: dict[str, Any],
        model_id: str | None = None,
    ) -> None:
        self._tools[name] = {
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": parameters,
            },
            "model_id": model_id,
        }

    def get_openai_specs(self) -> list[dict[str, Any]]:
        return [v for k, v in self._tools.items()]

    def get_tool(self, name: str) -> dict[str, Any] | None:
        return self._tools.get(name)

    async def execute_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        tool = self._tools.get(name)
        if tool is None:
            raise ValueError(f"Unknown tool: {name}")

        model_id = tool.get("model_id")
        if model_id:
            result = await self.orchestrator.infer(model_id, arguments)
            return result["output"]

        logger.warning("Tool %s has no model_id, returning stub", name)
        return {"stub": True}


def build_cv_tools(registry: ToolRegistry) -> None:
    registry.register_tool(
        name="detect_objects",
        description="Detect objects in the image (people, vehicles, etc.)",
        parameters={
            "type": "object",
            "properties": {
                "image": {"type": "string", "description": "Base64 encoded image"},
                "confidence": {"type": "number", "description": "Detection confidence threshold"},
            },
            "required": ["image"],
        },
        model_id="object_detection",
    )

    registry.register_tool(
        name="recognize_license_plate",
        description="Detect and recognize license plate number from image",
        parameters={
            "type": "object",
            "properties": {
                "image": {"type": "string", "description": "Base64 encoded image"},
            },
            "required": ["image"],
        },
        model_id="license_plate",
    )

    registry.register_tool(
        name="recognize_face",
        description="Detect face and recognize identity from image",
        parameters={
            "type": "object",
            "properties": {
                "image": {"type": "string", "description": "Base64 encoded image"},
            },
            "required": ["image"],
        },
        model_id="face_recognition",
    )

    registry.register_tool(
        name="detect_vehicle",
        description="Detect vehicle type (car/SUV/truck/bus) from image",
        parameters={
            "type": "object",
            "properties": {
                "image": {"type": "string", "description": "Base64 encoded image"},
            },
            "required": ["image"],
        },
        model_id="vehicle_detection",
    )

    registry.register_tool(
        name="ocr_text",
        description="Recognize text in natural scene image",
        parameters={
            "type": "object",
            "properties": {
                "image": {"type": "string", "description": "Base64 encoded image"},
            },
            "required": ["image"],
        },
        model_id="ocr",
    )

    registry.register_tool(
        name="match_person",
        description="Extract person features and match across cameras (ReID)",
        parameters={
            "type": "object",
            "properties": {
                "image": {"type": "string", "description": "Base64 encoded image"},
                "camera_id": {"type": "string", "description": "Source camera ID"},
            },
            "required": ["image"],
        },
        model_id="person_reid",
    )
