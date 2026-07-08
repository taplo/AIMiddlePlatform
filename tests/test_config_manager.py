from src.core.config_manager import ConfigManager


def test_get_existing_key() -> None:
    cm = ConfigManager()
    version = cm.get("app.version")
    assert version == "0.1.0"


def test_get_missing_key() -> None:
    cm = ConfigManager()
    assert cm.get("nonexistent.key") is None


def test_get_with_default() -> None:
    cm = ConfigManager()
    assert cm.get("nonexistent", 42) == 42


def test_set_and_get() -> None:
    cm = ConfigManager()
    cm.set("test.key", "value")
    assert cm.get("test.key") == "value"


def test_get_section() -> None:
    cm = ConfigManager()
    ingestion = cm.get_section("ingestion")
    assert ingestion["max_streams"] == 1000


def test_all_contains_sections() -> None:
    cm = ConfigManager()
    data = cm.all()
    assert "app" in data
    assert "ingestion" in data
    assert "queue" in data
