import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from src.models.package_manager import ModelPackageManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/model-packages", tags=["model-packages"])

_mgr: ModelPackageManager | None = None


def init_package_manager(mgr: ModelPackageManager) -> None:
    global _mgr
    _mgr = mgr


@router.get("/")
async def list_packages() -> list[dict]:
    if _mgr is None:
        return []
    return [{
        "model_id": p["model_id"],
        "name": p.get("name", p["model_id"]),
        "version": p["version"],
        "backend": p.get("backend", "onnx"),
        "package_size": p.get("package_size", 0),
        "tags": p.get("tags", []),
        "description": p.get("description", ""),
        "created_at": p.get("created_at", ""),
    } for p in _mgr.list_packages()]


@router.post("/upload")
async def upload_package(request: Request) -> dict:
    if _mgr is None:
        raise HTTPException(500, "Package manager not initialized")
    content = await request.body()
    filename = request.headers.get("X-Filename", "model.aimp")
    if not filename.endswith(".aimp"):
        raise HTTPException(400, "Invalid package format (must be .aimp)")
    dest = _mgr._store / filename
    dest.write_bytes(content)
    ok = _mgr.verify_package(dest)
    if not ok:
        dest.unlink()
        raise HTTPException(400, "Package verification failed")
    return {"ok": True, "package": filename, "size": len(content)}


@router.get("/{model_id}/{version}/download")
async def download_package(model_id: str, version: str):
    if _mgr is None:
        raise HTTPException(500, "Package manager not initialized")
    path = _mgr._package_path(model_id, version)
    if not path.exists():
        raise HTTPException(404, f"Package {model_id} v{version} not found")
    return FileResponse(
        path,
        media_type="application/gzip",
        filename=path.name,
    )


@router.delete("/{model_id}/{version}")
async def delete_package(model_id: str, version: str) -> dict:
    if _mgr is None:
        raise HTTPException(500, "Package manager not initialized")
    ok = _mgr.remove_package(model_id, version)
    if not ok:
        raise HTTPException(404, f"Package {model_id} v{version} not found")
    return {"ok": True}
