import tempfile
from pathlib import Path

import pytest

from src.models.package_manager import ModelPackageManager, ModelPackageManifest


@pytest.fixture
def sample_model_dir():
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        (d / "model.onnx").write_text("fake_onnx_content")
        (d / "labels.txt").write_text("person\ncar\nbus\n")
        labels_cn = d / "config"
        labels_cn.mkdir()
        (labels_cn / "labels_cn.txt").write_text("人\n车\n公交车\n")
        yield d


@pytest.fixture
def package_mgr():
    with tempfile.TemporaryDirectory() as tmp:
        yield ModelPackageManager(tmp)


class TestModelPackageManager:
    def test_build_package(self, package_mgr, sample_model_dir):
        path = package_mgr.build_package(
            model_dir=sample_model_dir,
            model_id="test_model",
            name="Test Model",
            version="1.0.0",
            backend="onnx",
            tags=["cv", "detection"],
            description="A test model",
        )
        assert path.exists()
        assert path.suffix == ".aimp"

    def test_build_and_extract(self, package_mgr, sample_model_dir):
        path = package_mgr.build_package(
            model_dir=sample_model_dir,
            model_id="test_model",
            name="Test Model",
            version="1.0.0",
        )
        with tempfile.TemporaryDirectory() as tmp:
            manifest = package_mgr.extract_package(path, tmp)
            assert manifest.model_id == "test_model"
            assert manifest.version == "1.0.0"
            assert len(manifest.files) == 3

    def test_list_packages(self, package_mgr, sample_model_dir):
        package_mgr.build_package(
            model_dir=sample_model_dir,
            model_id="model_a",
            name="Model A",
            version="1.0.0",
        )
        package_mgr.build_package(
            model_dir=sample_model_dir,
            model_id="model_b",
            name="Model B",
            version="2.0.0",
        )
        packages = package_mgr.list_packages()
        assert len(packages) == 2
        ids = {p["model_id"] for p in packages}
        assert ids == {"model_a", "model_b"}

    def test_remove_package(self, package_mgr, sample_model_dir):
        package_mgr.build_package(
            model_dir=sample_model_dir,
            model_id="test_model",
            name="Test",
            version="1.0.0",
        )
        assert package_mgr.remove_package("test_model", "1.0.0") is True
        assert package_mgr.remove_package("nonexistent", "1.0.0") is False
        assert len(package_mgr.list_packages()) == 0

    def test_verify_valid_package(self, package_mgr, sample_model_dir):
        path = package_mgr.build_package(
            model_dir=sample_model_dir,
            model_id="test_model",
            name="Test",
            version="1.0.0",
        )
        assert package_mgr.verify_package(path) is True

    def test_verify_tampered_package(self, package_mgr, sample_model_dir):
        import tarfile
        import tempfile
        path = package_mgr.build_package(
            model_dir=sample_model_dir,
            model_id="test_model",
            name="Test",
            version="1.0.0",
        )
        with tempfile.TemporaryDirectory() as tmp:
            extract_dir = Path(tmp) / "extracted"
            with tarfile.open(path, "r:gz") as tar:
                tar.extractall(path=extract_dir, filter="data")
            target = extract_dir / "model.onnx"
            target.write_text("TAMPERED_CONTENT")
            path.unlink()
            with tarfile.open(path, "w:gz") as tar:
                for f in extract_dir.rglob("*"):
                    if f.is_file():
                        tar.add(f, arcname=f.relative_to(extract_dir).as_posix())
        assert package_mgr.verify_package(path) is False


class TestModelPackageManifest:
    def test_serialization_roundtrip(self):
        manifest = ModelPackageManifest(
            model_id="test",
            name="Test",
            version="1.0.0",
            backend="onnx",
            tags=["cv"],
            files=[{"path": "model.onnx", "size": 100, "sha256": "abc"}],
            dependencies={"torch": ">=2.0"},
        )
        data = manifest.to_dict()
        restored = ModelPackageManifest.from_dict(data)
        assert restored.model_id == "test"
        assert restored.version == "1.0.0"
        assert restored.backend == "onnx"
        assert restored.dependencies == {"torch": ">=2.0"}

    def test_from_dict_minimal(self):
        data = {"model_id": "minimal", "version": "0.0.1"}
        manifest = ModelPackageManifest.from_dict(data)
        assert manifest.model_id == "minimal"
        assert manifest.version == "0.0.1"
        assert manifest.backend == "onnx"
