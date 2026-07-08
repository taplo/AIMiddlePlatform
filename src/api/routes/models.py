from fastapi import APIRouter, HTTPException

from src.models.registry import ModelRegistry, ModelSpec, ModelStatus

router = APIRouter(prefix="/v1/models", tags=["models"])

_registry: ModelRegistry | None = None


def init_registry(registry: ModelRegistry) -> None:
    global _registry
    _registry = registry


@router.get("/")
async def list_models(status: str | None = None) -> list[dict]:
    if _registry is None:
        return []
    status_filter = ModelStatus(status) if status else None
    return [_spec_to_dict(m) for m in _registry.list_models(status_filter)]


@router.get("/active")
async def active_models() -> list[dict]:
    if _registry is None:
        return []
    return [_spec_to_dict(m) for m in _registry.get_active_models()]


@router.get("/{model_id}")
async def get_model(model_id: str, version: str | None = None) -> dict:
    if _registry is None:
        raise HTTPException(404, "Registry not initialized")
    spec = _registry.get(model_id, version)
    if spec is None:
        raise HTTPException(404, f"Model {model_id} not found")
    return _spec_to_dict(spec)


@router.post("/{model_id}/status")
async def update_model_status(model_id: str, body: dict) -> dict:
    if _registry is None:
        raise HTTPException(500, "Registry not initialized")
    version = body.get("version", "")
    status = body.get("status", "online")
    _registry.set_status(model_id, version, ModelStatus(status))
    return {"ok": True, "model_id": model_id, "version": version, "status": status}


def _spec_to_dict(spec: ModelSpec) -> dict:
    return {
        "model_id": spec.model_id,
        "name": spec.name,
        "version": spec.version,
        "status": spec.status.value,
        "backend": spec.backend,
        "description": spec.description,
        "tags": spec.tags,
        "cost_estimate": spec.cost_estimate,
    }
