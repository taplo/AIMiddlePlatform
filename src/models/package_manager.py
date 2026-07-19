import hashlib
import json
import logging
import os
import shutil
import tarfile
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

PACKAGE_FORMAT_VERSION = "1.0"

MANIFEST_FILE = "manifest.json"
WEIGHTS_DIR = "weights"
CONFIG_DIR = "config"


@dataclass
class ModelPackageManifest:
    model_id: str
    name: str
    version: str
    format_version: str = PACKAGE_FORMAT_VERSION
    description: str = ""
    backend: str = "onnx"
    tags: list[str] = field(default_factory=list)
    files: list[dict[str, Any]] = field(default_factory=list)
    checksum: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    dependencies: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "name": self.name,
            "version": self.version,
            "format_version": self.format_version,
            "description": self.description,
            "backend": self.backend,
            "tags": self.tags,
            "files": self.files,
            "checksum": self.checksum,
            "created_at": self.created_at,
            "dependencies": self.dependencies,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ModelPackageManifest":
        return cls(
            model_id=data["model_id"],
            name=data.get("name", data["model_id"]),
            version=data["version"],
            format_version=data.get("format_version", PACKAGE_FORMAT_VERSION),
            description=data.get("description", ""),
            backend=data.get("backend", "onnx"),
            tags=data.get("tags", []),
            files=data.get("files", []),
            checksum=data.get("checksum", ""),
            created_at=data.get("created_at", datetime.now().isoformat()),
            dependencies=data.get("dependencies", {}),
        )


class ModelPackageManager:
    def __init__(self, store_path: str | Path):
        self._store = Path(store_path)
        self._store.mkdir(parents=True, exist_ok=True)
        self._cache: dict[str, ModelPackageManifest] = {}

    def _package_path(self, model_id: str, version: str) -> Path:
        return self._store / f"{model_id}-v{version}.aimp"

    def build_package(
        self,
        model_dir: str | Path,
        model_id: str,
        name: str,
        version: str,
        backend: str = "onnx",
        tags: list[str] | None = None,
        description: str = "",
        dependencies: dict[str, str] | None = None,
    ) -> Path:
        model_dir = Path(model_dir)
        if not model_dir.is_dir():
            raise ValueError(f"Model directory not found: {model_dir}")

        package_path = self._package_path(model_id, version)
        files_manifest: list[dict[str, Any]] = []

        for entry in sorted(model_dir.rglob("*")):
            if entry.is_file():
                sha256 = hashlib.sha256()
                sha256.update(entry.read_bytes())
                rel = entry.relative_to(model_dir).as_posix()
                files_manifest.append({
                    "path": rel,
                    "size": entry.stat().st_size,
                    "sha256": sha256.hexdigest(),
                })

        manifest = ModelPackageManifest(
            model_id=model_id,
            name=name,
            version=version,
            description=description,
            backend=backend,
            tags=tags or [],
            files=files_manifest,
            dependencies=dependencies or {},
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)

            manifest_path = tmp / MANIFEST_FILE
            manifest_path.write_text(
                json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            with tarfile.open(package_path, "w:gz") as tar:
                tar.add(manifest_path, arcname=MANIFEST_FILE)
                for entry in sorted(model_dir.rglob("*")):
                    if entry.is_file():
                        tar.add(entry, arcname=entry.relative_to(model_dir).as_posix())

        logger.info(
            "Package built: %s (model=%s v%s, files=%d)",
            package_path, model_id, version, len(files_manifest),
        )
        return package_path

    def extract_package(
        self,
        package_path: str | Path,
        output_dir: str | Path,
    ) -> ModelPackageManifest:
        package_path = Path(package_path)
        if not package_path.exists():
            raise FileNotFoundError(f"Package not found: {package_path}")

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        with tarfile.open(package_path, "r:gz") as tar:
            tar.extractall(path=output_dir, filter="data")

        manifest_file = output_dir / MANIFEST_FILE
        if not manifest_file.exists():
            raise ValueError(f"Invalid package: missing {MANIFEST_FILE}")

        manifest = ModelPackageManifest.from_dict(
            json.loads(manifest_file.read_text(encoding="utf-8"))
        )
        logger.info(
            "Package extracted: %s -> %s (model=%s v%s)",
            package_path, output_dir, manifest.model_id, manifest.version,
        )
        return manifest

    def install_package(
        self,
        package_path: str | Path,
        target_dir: str | Path | None = None,
    ) -> ModelPackageManifest:
        package_path = Path(package_path)
        extract_dir = package_path.parent / f".extract-{package_path.stem}"
        manifest = self.extract_package(package_path, extract_dir)
        package_path.unlink()

        if target_dir is None:
            target_dir = self._store / "installed" / manifest.model_id / manifest.version
        else:
            target_dir = Path(target_dir)

        target_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(extract_dir, target_dir, dirs_exist_ok=True)
        shutil.rmtree(extract_dir, ignore_errors=True)
        return manifest

    def list_packages(self) -> list[dict[str, Any]]:
        packages = []
        for f in sorted(self._store.glob("*.aimp")):
            try:
                with tarfile.open(f, "r:gz") as tar:
                    member = tar.getmember(MANIFEST_FILE)
                    f_obj = tar.extractfile(member)
                    if f_obj:
                        manifest = ModelPackageManifest.from_dict(
                            json.loads(f_obj.read().decode("utf-8"))
                        )
                        packages.append({
                            **manifest.to_dict(),
                            "package_size": f.stat().st_size,
                            "package_path": str(f),
                        })
            except Exception as e:
                logger.warning("Failed to read package %s: %s", f.name, e)
        return packages

    def remove_package(self, model_id: str, version: str) -> bool:
        package_path = self._package_path(model_id, version)
        if package_path.exists():
            package_path.unlink()
            logger.info("Package removed: %s", package_path)
            return True
        logger.warning("Package not found: %s", package_path)
        return False

    def verify_package(self, package_path: str | Path) -> bool:
        package_path = Path(package_path)
        try:
            with tarfile.open(package_path, "r:gz") as tar:
                member = tar.getmember(MANIFEST_FILE)
                f_obj = tar.extractfile(member)
                if not f_obj:
                    return False
                manifest = ModelPackageManifest.from_dict(
                    json.loads(f_obj.read().decode("utf-8"))
                )
                for entry in manifest.files:
                    try:
                        m = tar.getmember(entry["path"])
                        f2 = tar.extractfile(m)
                        if f2:
                            sha256 = hashlib.sha256()
                            sha256.update(f2.read())
                            if sha256.hexdigest() != entry["sha256"]:
                                logger.warning(
                                    "Checksum mismatch: %s", entry["path"]
                                )
                                return False
                    except KeyError:
                        logger.warning("Missing file: %s", entry["path"])
                        return False
            return True
        except Exception as e:
            logger.error("Package verification failed: %s", e)
            return False
