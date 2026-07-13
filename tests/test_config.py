from src.core.config import settings


def test_get_existing_key():
    val = settings.get("app.version")
    assert val == "0.1.0"


def test_get_missing_key():
    assert settings.get("nonexistent.key") is None


def test_get_with_default():
    assert settings.get("nonexistent", 42) == 42


def test_get_section():
    val = settings.get("ingestion")
    assert isinstance(val, dict)
    assert val["max_streams"] == 10
