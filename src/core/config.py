import os
from pathlib import Path

import yaml


class Settings:
    def __init__(self) -> None:
        self._config: dict = {}
        self._load()

    def _load(self) -> None:
        env = os.getenv("APP_ENV", "dev")
        config_dir = Path(__file__).parent.parent.parent / "config"
        default_path = config_dir / "default.yaml"
        env_path = config_dir / f"{env}.yaml"

        if default_path.exists():
            with open(default_path) as f:
                self._config.update(yaml.safe_load(f) or {})
        if env_path.exists():
            with open(env_path) as f:
                env_config = yaml.safe_load(f) or {}
                self._config.update(env_config)

    def get(self, key: str, default=None):
        keys = key.split(".")
        value = self._config
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default
        if value is None:
            return default
        return value


settings = Settings()
