from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

router = APIRouter()


TOKEN_TTL_SECONDS = int(os.getenv("QUANTGRID_TOKEN_TTL_SECONDS", "28800"))
ALL_ROLES = {"admin", "trader", "analyst", "viewer", "ops"}


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    expires_at: int


def _auth_secret() -> bytes:
    secret = os.getenv("QUANTGRID_AUTH_SECRET")
    if not secret:
        secret = "quantgrid-local-dev-secret"
    return secret.encode("utf-8")


def _configured_users() -> dict[str, tuple[str, str]]:
    configured = os.getenv("QUANTGRID_USERS", "viewer:viewer:viewer")
    users: dict[str, tuple[str, str]] = {}

    for item in configured.split(","):
        parts = [part.strip() for part in item.split(":")]
        if len(parts) != 3:
            continue
        username, password, role = parts
        role = role.lower()
        if username and password and role in ALL_ROLES:
            users[username] = (password, role)

    return users


def _b64encode(payload: bytes) -> str:
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def _b64decode(payload: str) -> bytes:
    padding = "=" * (-len(payload) % 4)
    return base64.urlsafe_b64decode(payload + padding)


def _sign(payload: str) -> str:
    digest = hmac.new(_auth_secret(), payload.encode("ascii"), hashlib.sha256).digest()
    return _b64encode(digest)


def create_token(username: str, role: str) -> tuple[str, int]:
    expires_at = int(time.time()) + TOKEN_TTL_SECONDS
    payload = _b64encode(
        json.dumps(
            {"sub": username, "role": role, "exp": expires_at},
            separators=(",", ":"),
        ).encode("utf-8")
    )
    return f"{payload}.{_sign(payload)}", expires_at


def verify_token(token: str) -> dict[str, Any]:
    try:
        payload, signature = token.split(".", 1)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc

    if not hmac.compare_digest(signature, _sign(payload)):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    try:
        claims = json.loads(_b64decode(payload).decode("utf-8"))
    except (ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc

    if int(claims.get("exp", 0)) < int(time.time()):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")

    role = str(claims.get("role", "")).lower()
    if role not in ALL_ROLES:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid role")

    return claims


@router.post("/login")
def login(payload: LoginRequest) -> TokenResponse:
    users = _configured_users()
    username = payload.username.strip()
    stored = users.get(username)

    if stored is None or not hmac.compare_digest(stored[0], payload.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    token, expires_at = create_token(username, stored[1])
    return TokenResponse(access_token=token, role=stored[1], expires_at=expires_at)
