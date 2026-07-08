from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Any

import yaml


class ConfigManager:
    def __init__(self, config_dir: str = "") -> None:
        self._config_dir = Path(config_dir) if config_dir else Path(__file__).parent.parent.parent / "config"
        self._lock = Lock()
        self._data: dict[str, Any] = {}
        self._mtime_map: dict[str, float] = {}
        self._load_all()

    def _load_all(self) -> None:
        self._data.clear()
        self._mtime_map.clear()
        for yaml_path in sorted(self._config_dir.glob("*.yaml")):
            self._load_file(yaml_path)

    def _load_file(self, path: Path) -> bool:
        if not path.exists():
            return False
        try:
            with open(path) as f:
                cfg = yaml.safe_load(f) or {}
            with self._lock:
                self._deep_merge(self._data, cfg)
            self._mtime_map[str(path)] = path.stat().st_mtime
            return True
        except Exception:
            return False

    def _deep_merge(self, base: dict, overlay: dict) -> None:
        for key, value in overlay.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._deep_merge(base[key], value)
            else:
                base[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        keys = key.split(".")
        value = self._data
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default
        if value is None:
            return default
        return value

    def set(self, key: str, value: Any) -> None:
        keys = key.split(".")
        target = self._data
        for k in keys[:-1]:
            target = target.setdefault(k, {})
        target[keys[-1]] = value

    def all(self) -> dict:
        return dict(self._data)

    def check_reload(self) -> bool:
        changed = False
        for yaml_path in self._config_dir.glob("*.yaml"):
            path_str = str(yaml_path)
            mtime = yaml_path.stat().st_mtime
            if mtime > self._mtime_map.get(path_str, 0):
                if self._load_file(yaml_path):
                    changed = True
        return changed

    def get_section(self, section: str) -> dict:
        return self.get(section) or {}


config_manager = ConfigManager()
