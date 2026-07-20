import os
from pathlib import Path

import yaml

_ENV_KEY_MAP: dict[str, str] = {
    "queue.redis_url": "QUEUE_REDIS_URL",
    "database.url": "DATABASE_URL",
    "llm.api_key": "LLM_API_KEY",
    "llm.api_url": "LLM_API_URL",
    "llm.model_name": "LLM_MODEL_NAME",
    "storage.endpoint": "S3_ENDPOINT",
    "storage.access_key": "S3_ACCESS_KEY",
    "storage.secret_key": "S3_SECRET_KEY",
    "storage.bucket": "S3_BUCKET",
    "result_cache.ttl_seconds": "CACHE_TTL_SECONDS",
    "result_cache.enabled": "CACHE_ENABLED",
    "websocket.enabled": "WS_ENABLED",
    "websocket.max_connections": "WS_MAX_CONNECTIONS",
    "app.env": "APP_ENV",
    "ingestion.max_streams": "MAX_STREAMS",
    "rate_limiter.default_rate": "RATE_LIMIT_DEFAULT",
    "worker.max_concurrent": "WORKER_MAX_CONCURRENT",
    "worker.db_queue_size": "WORKER_DB_QUEUE_SIZE",
    "worker.rule_queue_size": "WORKER_RULE_QUEUE_SIZE",
}


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
                self._deep_merge(self._config, env_config)

    def _deep_merge(self, base: dict, overlay: dict) -> None:
        for key, value in overlay.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._deep_merge(base[key], value)
            else:
                base[key] = value

    def get(self, key: str, default=None):
        env_var = _ENV_KEY_MAP.get(key)
        if env_var:
            env_value = os.getenv(env_var)
            if env_value is not None:
                return self._coerce(env_value)
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

    @staticmethod
    def _coerce(value: str):
        if value.lower() in ("true", "1", "yes"):
            return True
        if value.lower() in ("false", "0", "no"):
            return False
        try:
            return int(value)
        except ValueError:
            pass
        try:
            return float(value)
        except ValueError:
            pass
        return value


settings = Settings()
