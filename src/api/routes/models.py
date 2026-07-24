import logging
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from src.models.registry import ModelRegistry, ModelSpec, ModelStatus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/models", tags=["models"])

_registry: ModelRegistry | None = None
_models_dir: Path | None = None


def init_registry(registry: ModelRegistry, models_dir: str | Path | None = None) -> None:
    global _registry, _models_dir
    _registry = registry
    if models_dir:
        _models_dir = Path(models_dir)


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


@router.post("/")
async def register_model(body: dict) -> dict:
    if _registry is None:
        raise HTTPException(500, "Registry not initialized")
    spec = ModelSpec(
        model_id=body["model_id"],
        name=body.get("name", body["model_id"]),
        version=body.get("version", "1.0.0"),
        description=body.get("description", ""),
        backend=body.get("backend", "onnx"),
        tags=body.get("tags", []),
        cost_estimate=body.get("cost_estimate", "medium"),
    )
    _registry.register(spec)
    return _spec_to_dict(spec)


@router.post("/upload")
async def upload_model_file(
    file: UploadFile = File(...),
    model_id: str = Form(...),
    name: str = Form(""),
    version: str = Form("1.0.0"),
    description: str = Form(""),
    backend: str = Form("onnx"),
    tags: str = Form(""),
):
    if _registry is None:
        raise HTTPException(500, "Registry not initialized")
    if not file.filename:
        raise HTTPException(400, "No file provided")

    tag_list = [t.strip() for t in tags.split(",") if t.strip()]

    models_root = _models_dir or Path("models")
    models_root.mkdir(parents=True, exist_ok=True)

    ext = Path(file.filename).suffix
    dest = models_root / f"{model_id}{ext}"
    content = await file.read()
    dest.write_bytes(content)

    spec = ModelSpec(
        model_id=model_id,
        name=name or model_id,
        version=version,
        description=description,
        backend=backend,
        tags=tag_list,
    )
    _registry.register(spec)
    logger.info("Model file uploaded: %s (%s, %d bytes)", dest.name, backend, len(content))

    return {**_spec_to_dict(spec), "file_path": str(dest), "file_size": len(content)}


@router.delete("/{model_id}")
async def delete_model(model_id: str, version: str | None = None) -> dict:
    if _registry is None:
        raise HTTPException(500, "Registry not initialized")
    spec = _registry.get(model_id, version)
    if spec is None:
        raise HTTPException(404, f"Model {model_id} not found")
    _registry.remove(model_id, version)

    models_root = _models_dir or Path("models")
    for f in models_root.glob(f"{model_id}.*"):
        f.unlink()
        logger.info("Deleted model file: %s", f)

    return {"ok": True, "model_id": model_id, "version": version or "all"}


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
