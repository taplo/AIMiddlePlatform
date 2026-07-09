import os
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from jose import jwt, JWTError

router = APIRouter(prefix="/api/v1/auth", tags=["admin-auth"])

SECRET_KEY = os.getenv("JWT_SECRET_KEY", "aimp-dev-secret-change-in-production")
ALGORITHM = "HS256"
ACCESS_EXPIRE = timedelta(hours=24)
REFRESH_EXPIRE = timedelta(days=7)

_ADMIN_USER = "admin"
_ADMIN_PASS = "admin123"


class LoginRequest(BaseModel):
    username: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str | None = None


def _create_token(data: dict, expires_delta: timedelta) -> str:
    payload = data.copy()
    payload["exp"] = datetime.now(timezone.utc) + expires_delta
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest) -> TokenResponse:
    if body.username != _ADMIN_USER or body.password != _ADMIN_PASS:
        raise HTTPException(401, "Invalid credentials")
    access = _create_token({"sub": body.username}, ACCESS_EXPIRE)
    refresh = _create_token({"sub": body.username, "type": "refresh"}, REFRESH_EXPIRE)
    return TokenResponse(access_token=access, refresh_token=refresh)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest) -> TokenResponse:
    try:
        payload = jwt.decode(body.refresh_token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != "refresh":
            raise HTTPException(401, "Invalid token type")
        access = _create_token({"sub": payload["sub"]}, ACCESS_EXPIRE)
        return TokenResponse(access_token=access)
    except JWTError:
        raise HTTPException(401, "Invalid or expired token")


def get_current_user(token: str) -> str:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload.get("sub", "unknown")
    except JWTError:
        raise HTTPException(401, "Invalid or expired token")
