import hashlib
import logging
import os
import time
from typing import Any

logger = logging.getLogger(__name__)

BUSINESS_PREFIXES = ("/api/v1/analyze", "/api/v1/tasks", "/api/v1/alerts", "/api/v1/video-cache", "/api/v1/models", "/api/v1/routing", "/api/v1/config",
                     "/v1/analyze", "/v1/tasks", "/v1/alerts", "/v1/video-cache", "/v1/models", "/v1/routing", "/v1/config")
ADMIN_PREFIXES = ("/api/v1/admin", "/api/v1/auth", "/api/v1/system")
EXEMPT_PATHS = {"/api/v1/auth/login", "/api/v1/auth/refresh", "/api/v1/analyze/ping", "/v1/analyze/ping", "/metrics", "/health"}

RATE_LIMIT_HEADER = "X-RateLimit-Remaining"


class APIKeyStore:
    def __init__(self) -> None:
        self._keys: dict[str, dict[str, Any]] = {}

    def load_from_env(self) -> None:
        raw = os.getenv("API_KEYS", "")
        if raw:
            for entry in raw.split(";"):
                parts = entry.strip().split(":")
                if len(parts) >= 2:
                    name, key = parts[0], parts[1]
                    rate = int(parts[2]) if len(parts) >= 3 else 10
                    self.add_key(name, key, rate)

    def add_key(self, name: str, key: str, rate_per_second: int = 10) -> None:
        if len(key) < 8:
            raise ValueError("API key must be at least 8 characters")
        self._keys[key] = {"name": name, "rate_per_second": rate_per_second}
        logger.info("API key added: %s (rate=%d/s)", name, rate_per_second)

    def remove_key(self, key: str) -> bool:
        return self._keys.pop(key, None) is not None

    def validate(self, key: str) -> dict[str, Any] | None:
        return self._keys.get(key)

    def list_keys(self) -> list[dict[str, Any]]:
        return [
            {"name": info["name"], "key_prefix": k[:8] + "...", "rate_per_second": info["rate_per_second"]}
            for k, info in self._keys.items()
        ]

    def count(self) -> int:
        return len(self._keys)


class TokenBucket:
    def __init__(self, rate_per_second: float, burst: int | None = None) -> None:
        self.rate = rate_per_second
        self.burst = max(burst or rate_per_second, 1)
        self._tokens = float(self.burst)
        self._last = time.monotonic()

    def consume(self, tokens: int = 1) -> bool:
        now = time.monotonic()
        elapsed = now - self._last
        self._tokens = min(float(self.burst), self._tokens + elapsed * self.rate)
        self._last = now
        if self._tokens >= tokens:
            self._tokens -= tokens
            return True
        return False

    def remaining(self) -> float:
        now = time.monotonic()
        elapsed = now - self._last
        return min(float(self.burst), self._tokens + elapsed * self.rate)


class RateLimiter:
    def __init__(self) -> None:
        self._buckets: dict[str, TokenBucket] = {}

    def check(self, key: str, rate_per_second: float = 10, tokens: int = 1) -> tuple[bool, int]:
        if key not in self._buckets or self._buckets[key].rate != rate_per_second:
            self._buckets[key] = TokenBucket(rate_per_second)
        allowed = self._buckets[key].consume(tokens)
        remaining = int(self._buckets[key].remaining())
        return allowed, remaining

    def reset(self, key: str) -> None:
        self._buckets.pop(key, None)


_api_key_store: APIKeyStore | None = None
_rate_limiter: RateLimiter | None = None


def init_security() -> tuple[APIKeyStore, RateLimiter]:
    global _api_key_store, _rate_limiter
    store = APIKeyStore()
    store.load_from_env()
    _api_key_store = store
    _rate_limiter = RateLimiter()
    logger.info("Security initialized: %d API keys loaded", store.count())
    return store, _rate_limiter


def get_api_key_store() -> APIKeyStore:
    global _api_key_store
    if _api_key_store is None:
        _api_key_store = APIKeyStore()
    return _api_key_store


def get_rate_limiter() -> RateLimiter:
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter()
    return _rate_limiter


def is_business_path(path: str) -> bool:
    return any(path.startswith(p) for p in BUSINESS_PREFIXES)


def is_admin_path(path: str) -> bool:
    return any(path.startswith(p) for p in ADMIN_PREFIXES)


def is_exempt_path(path: str) -> bool:
    return path in EXEMPT_PATHS or path.startswith("/api/v1/analyze/ping")
