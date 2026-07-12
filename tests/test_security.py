import time

import pytest
from fastapi.testclient import TestClient

from src.api.app import app
from src.core.security import (
    APIKeyStore,
    TokenBucket,
    RateLimiter,
    init_security,
    get_api_key_store,
    get_rate_limiter,
    is_business_path,
    is_admin_path,
    is_exempt_path,
)

client = TestClient(app)


def test_api_key_store_add_validate() -> None:
    store = APIKeyStore()
    store.add_key("test-key", "sk-test12345678", rate_per_second=5)
    info = store.validate("sk-test12345678")
    assert info is not None
    assert info["name"] == "test-key"
    assert info["rate_per_second"] == 5


def test_api_key_store_invalid_key() -> None:
    store = APIKeyStore()
    store.add_key("test", "valid-key-123456", rate_per_second=5)
    assert store.validate("wrong-key") is None


def test_api_key_store_remove() -> None:
    store = APIKeyStore()
    store.add_key("test", "remove-me-12345678")
    assert store.count() == 1
    assert store.remove_key("remove-me-12345678") is True
    assert store.count() == 0


def test_api_key_store_short_key_raises() -> None:
    store = APIKeyStore()
    with pytest.raises(ValueError):
        store.add_key("test", "short")


def test_api_key_store_list() -> None:
    store = APIKeyStore()
    store.add_key("key-a", "abcdefgh12345678", rate_per_second=10)
    store.add_key("key-b", "ijklmnop12345678", rate_per_second=20)
    keys = store.list_keys()
    assert len(keys) == 2
    for k in keys:
        assert "key_prefix" in k
        assert "rate_per_second" in k


def test_token_bucket_allows_requests() -> None:
    bucket = TokenBucket(rate_per_second=100, burst=10)
    for _ in range(10):
        assert bucket.consume() is True


def test_token_bucket_blocks_excess() -> None:
    bucket = TokenBucket(rate_per_second=1000, burst=2)
    assert bucket.consume() is True
    assert bucket.consume() is True
    assert bucket.consume() is False


def test_token_bucket_refills() -> None:
    bucket = TokenBucket(rate_per_second=10, burst=1)
    assert bucket.consume() is True
    assert bucket.consume() is False
    time.sleep(0.15)
    assert bucket.consume() is True


def test_rate_limiter_check() -> None:
    limiter = RateLimiter()
    allowed, remaining = limiter.check("key-1", rate_per_second=100)
    assert allowed is True
    assert remaining > 0


def test_rate_limiter_blocks() -> None:
    limiter = RateLimiter()
    limiter.check("limited", rate_per_second=0.01, tokens=1)
    allowed, _ = limiter.check("limited", rate_per_second=0.01, tokens=1)
    assert allowed is False


def test_rate_limiter_reset() -> None:
    limiter = RateLimiter()
    limiter.check("key-1", rate_per_second=1, tokens=1)
    limiter.reset("key-1")
    allowed, _ = limiter.check("key-1", rate_per_second=1, tokens=1)
    assert allowed is True


def test_init_security() -> None:
    store, limiter = init_security()
    assert store.count() >= 0
    assert isinstance(limiter, RateLimiter)


def test_path_classification() -> None:
    assert is_business_path("/api/v1/analyze/frame") is True
    assert is_business_path("/api/v1/tasks") is True
    assert is_business_path("/api/v1/alerts") is True
    assert is_admin_path("/api/v1/admin/dashboard") is True
    assert is_admin_path("/api/v1/auth/login") is True
    assert is_exempt_path("/api/v1/auth/login") is True
    assert is_exempt_path("/api/v1/analyze/ping") is True
    assert is_exempt_path("/metrics") is True
    assert is_business_path("/api/v1/health") is False
    assert is_admin_path("/api/v1/analyze/frame") is False


def test_middleware_requires_auth() -> None:
    resp = client.get("/v1/tasks")
    assert resp.status_code == 401
    assert "Authentication required" in resp.text


def test_middleware_rejects_invalid_api_key() -> None:
    resp = client.get("/v1/tasks", headers={"X-API-Key": "invalid"})
    assert resp.status_code == 401
    assert "Invalid API key" in resp.text


def test_middleware_valid_api_key_passes() -> None:
    store = get_api_key_store()
    store.add_key("test", "valid-key-12345678", rate_per_second=100)
    resp = client.get("/v1/tasks", headers={"X-API-Key": "valid-key-12345678"})
    assert resp.status_code in (200, 500)
    if resp.status_code == 200:
        assert "X-RateLimit-Remaining" in resp.headers


def test_middleware_exempt_paths_skip_auth() -> None:
    resp = client.get("/v1/analyze/ping")
    assert resp.status_code == 200


def test_middleware_rate_limit_exceeded() -> None:
    store = get_api_key_store()
    store.add_key("ratelimit-test", "rate-limited-key-999", rate_per_second=0.01)
    resp = client.get("/v1/tasks", headers={"X-API-Key": "rate-limited-key-999"})
    assert resp.status_code in (200, 500)
    resp2 = client.get("/v1/tasks", headers={"X-API-Key": "rate-limited-key-999"})
    assert resp2.status_code == 429


def test_middleware_jwt_still_works_for_business() -> None:
    resp_login = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"})
    if resp_login.status_code != 200:
        pytest.skip("Admin auth not available")
    token = resp_login.json()["access_token"]
    resp = client.get("/v1/tasks", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code in (200, 500)


def test_middleware_api_key_blocked_from_admin() -> None:
    store = get_api_key_store()
    store.add_key("admin-block", "admin-block-key-12345", rate_per_second=100)
    resp = client.get("/api/v1/admin/dashboard", headers={"X-API-Key": "admin-block-key-12345"})
    assert resp.status_code == 403
