from fastapi.testclient import TestClient

from src.api.app import app

client = TestClient(app)


def test_login_success() -> None:
    resp = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"})
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data


def test_login_invalid_credentials() -> None:
    resp = client.post("/api/v1/auth/login", json={"username": "admin", "password": "wrong"})
    assert resp.status_code == 401


def test_access_protected_route_without_token() -> None:
    resp = client.get("/api/v1/system/stats")
    assert resp.status_code == 401


def test_access_protected_route_with_valid_token() -> None:
    login_resp = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"})
    token = login_resp.json()["access_token"]
    resp = client.get("/api/v1/system/stats", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code != 401


def test_refresh_token() -> None:
    login_resp = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"})
    refresh = login_resp.json()["refresh_token"]
    resp = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
    assert resp.status_code == 200
    assert "access_token" in resp.json()
