import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class ModelStatus(Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    DEPRECATED = "deprecated"


@dataclass
class ModelSpec:
    model_id: str
    name: str
    version: str
    description: str = ""
    status: ModelStatus = ModelStatus.ONLINE
    backend: str = "onnx"
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)
    cost_estimate: str = "medium"
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    tags: list[str] = field(default_factory=list)


class ModelRegistry:
    def __init__(self) -> None:
        self._models: dict[str, list[ModelSpec]] = {}

    def register(self, spec: ModelSpec) -> None:
        if spec.model_id not in self._models:
            self._models[spec.model_id] = []
        self._models[spec.model_id].append(spec)
        logger.info("Model registered: %s v%s", spec.model_id, spec.version)

    def get(self, model_id: str, version: str | None = None) -> ModelSpec | None:
        versions = self._models.get(model_id)
        if not versions:
            return None
        if version:
            return next((v for v in versions if v.version == version), None)
        return versions[-1]

    def list_models(self, status: ModelStatus | None = None) -> list[ModelSpec]:
        all_models = [m for versions in self._models.values() for m in versions]
        if status:
            return [m for m in all_models if m.status == status]
        return all_models

    def set_status(self, model_id: str, version: str, status: ModelStatus) -> None:
        model = self.get(model_id, version)
        if model:
            model.status = status
            model.updated_at = datetime.now()

    def remove(self, model_id: str, version: str | None = None) -> bool:
        if version:
            versions = self._models.get(model_id, [])
            orig = len(versions)
            self._models[model_id] = [v for v in versions if v.version != version]
            if not self._models[model_id]:
                del self._models[model_id]
            return len(self._models.get(model_id, [])) < orig
        return self._models.pop(model_id, None) is not None

    def get_active_models(self) -> list[ModelSpec]:
        return [m for m in self.list_models() if m.status == ModelStatus.ONLINE]
