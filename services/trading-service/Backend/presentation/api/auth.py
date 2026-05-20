from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel

router = APIRouter()


TOKEN_TTL_SECONDS = int(os.getenv("QUANTGRID_TOKEN_TTL_SECONDS", "28800"))
ALL_ROLES = {"admin", "trader", "analyst", "viewer", "ops"}
DATA_DIR = Path(__file__).resolve().parents[2] / "data"
USERS_FILE = Path(os.getenv("QUANTGRID_USERS_FILE", DATA_DIR / "auth_users.json"))


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    expires_at: int


class CreateUserRequest(BaseModel):
    username: str
    password: str
    role: str


class UserResponse(BaseModel):
    username: str
    role: str


def _auth_secret() -> bytes:
    secret = os.getenv("QUANTGRID_AUTH_SECRET")
    if not secret:
        secret = "quantgrid-local-dev-secret"
    return secret.encode("utf-8")


def _password_hash(username: str, password: str) -> str:
    message = f"{username}:{password}".encode("utf-8")
    return hmac.new(_auth_secret(), message, hashlib.sha256).hexdigest()


def _default_users() -> dict[str, dict[str, str]]:
    configured = os.getenv(
        "QUANTGRID_USERS",
        "admin:admin123:admin,trader:trader123:trader,analyst:analyst123:analyst,viewer:viewer:viewer",
    )
    users: dict[str, dict[str, str]] = {}

    for item in configured.split(","):
        parts = [part.strip() for part in item.split(":")]
        if len(parts) != 3:
            continue
        username, password, role = parts
        role = role.lower()
        if username and password and role in ALL_ROLES:
            users[username] = {
                "password_hash": _password_hash(username, password),
                "role": role,
            }

    return users


def _read_user_store() -> dict[str, dict[str, str]]:
    if not USERS_FILE.exists():
        return {}

    try:
        stored = json.loads(USERS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}

    users: dict[str, dict[str, str]] = {}
    if not isinstance(stored, dict):
        return users

    for username, record in stored.items():
        if not isinstance(username, str) or not isinstance(record, dict):
            continue
        password_hash = str(record.get("password_hash") or "")
        role = str(record.get("role") or "").lower()
        if username and password_hash and role in ALL_ROLES:
            users[username] = {"password_hash": password_hash, "role": role}

    return users


def _write_user_store(users: dict[str, dict[str, str]]) -> None:
    USERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    USERS_FILE.write_text(json.dumps(users, indent=2, sort_keys=True), encoding="utf-8")


def _configured_users() -> dict[str, dict[str, str]]:
    return {**_default_users(), **_read_user_store()}


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


def _require_admin(authorization: str | None = Header(default=None)) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
        )

    claims = verify_token(authorization.split(" ", 1)[1].strip())
    if str(claims.get("role", "")).lower() != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can create users.",
        )
    return str(claims.get("sub") or "")


@router.post("/login")
def login(payload: LoginRequest) -> TokenResponse:
    users = _configured_users()
    username = payload.username.strip()
    stored = users.get(username)

    if stored is None or not hmac.compare_digest(
        stored["password_hash"],
        _password_hash(username, payload.password),
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    token, expires_at = create_token(username, stored["role"])
    return TokenResponse(access_token=token, role=stored["role"], expires_at=expires_at)


@router.post("/users", response_model=UserResponse)
def create_user(payload: CreateUserRequest, _admin: str = Depends(_require_admin)) -> UserResponse:
    username = payload.username.strip()
    password = payload.password
    role = payload.role.strip().lower()

    if not username:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username is required.")
    if len(password) < 6:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Password must be at least 6 characters.")
    if role not in ALL_ROLES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid role.")

    users = _read_user_store()
    if username in _configured_users():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User already exists.")

    users[username] = {
        "password_hash": _password_hash(username, password),
        "role": role,
    }
    _write_user_store(users)

    return UserResponse(username=username, role=role)
