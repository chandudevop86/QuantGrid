from __future__ import annotations

import base64
import json
import time
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from Backend.core.config import get_settings
from Backend.core.database import get_db, init_database
from Backend.domain.security.audit import request_ip, write_audit_log
from Backend.domain.security.models import User
from Backend.domain.security.passwords import hash_password, validate_password_policy, verify_password
from Backend.domain.security.rate_limit import rate_limiter

router = APIRouter()
admin_router = APIRouter()

TOKEN_TTL_SECONDS = 28800
ALL_ROLES = {"admin", "developer", "trader", "analyst", "viewer", "ops"}
TRADE_EXECUTE_ROLES = {"admin", "trader"}


class LoginRequest(BaseModel):
    username: str
    password: str


class RegistrationRequest(BaseModel):
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


class ResetPasswordRequest(BaseModel):
    password: str


class ChangePasswordRequest(BaseModel):
    old_password: str | None = None
    new_password: str


class UserResponse(BaseModel):
    id: int
    username: str
    role: str


def init_auth_store() -> None:
    init_database()
    from Backend.core.database import SessionLocal
    from Backend.domain.security.audit import ensure_audit_schema

    with SessionLocal() as db:
        ensure_audit_schema(db)


def _b64encode(payload: bytes) -> str:
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def _b64decode(payload: str) -> bytes:
    padding = "=" * (-len(payload) % 4)
    return base64.urlsafe_b64decode(payload + padding)


def _sign(payload: str) -> str:
    import hashlib
    import hmac

    digest = hmac.new(get_settings().auth_secret.encode("utf-8"), payload.encode("ascii"), hashlib.sha256).digest()
    return _b64encode(digest)


def create_token(user: User) -> tuple[str, int]:
    expires_at = int(time.time()) + TOKEN_TTL_SECONDS
    payload = _b64encode(
        json.dumps(
            {"sub": user.username, "uid": user.id, "role": user.role, "exp": expires_at},
            separators=(",", ":"),
        ).encode("utf-8")
    )
    return f"{payload}.{_sign(payload)}", expires_at


def verify_token(token: str) -> dict[str, Any]:
    import hmac

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


def _user_response(user: User) -> UserResponse:
    return UserResponse(id=user.id, username=user.username, role=user.role)


def _rate_key(*parts: object | None) -> str:
    return ":".join(str(part or "-").lower() for part in parts)


def _find_user_by_username(db: Session, username: str) -> User | None:
    return db.query(User).filter(User.username == username).one_or_none()


def _find_user_by_id(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    return user


def current_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")

    claims = verify_token(authorization.split(" ", 1)[1].strip())
    user = db.get(User, int(claims["uid"]))
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User no longer exists")
    return user


def require_admin(
    request: Request,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> User:
    if user.role != "admin":
        write_audit_log(
            db,
            action="admin_action_failed",
            actor=user,
            target_type="permission",
            target_id="admin",
            request=request,
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only admins can perform this action.")
    return user


def require_trade_execute(
    request: Request,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> User:
    if user.role not in TRADE_EXECUTE_ROLES:
        write_audit_log(
            db,
            action="execution_blocked",
            actor=user,
            target_type="permission",
            target_id="trade_execute",
            request=request,
            metadata={"reason": "missing trade_execute permission"},
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User lacks trade_execute permission.")
    return user


def require_roles(*allowed_roles: str):
    allowed = set(allowed_roles)

    def dependency(user: User = Depends(current_user)) -> str:
        if user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This role is not allowed to perform this action.",
            )
        return user.role

    return dependency


def seed_bootstrap_users(db: Session) -> None:
    settings = get_settings()
    if not settings.bootstrap_users or not settings.allow_dev_seed_users:
        return

    for item in settings.bootstrap_users.split(","):
        parts = [part.strip() for part in item.split(":")]
        if len(parts) != 3:
            continue
        username, password, role = parts
        if role not in ALL_ROLES:
            continue
        validate_password_policy(password)
        user = _find_user_by_username(db, username)
        if user is None:
            db.add(User(username=username, password_hash=hash_password(password), role=role))
            continue
        user.password_hash = hash_password(password)
        user.role = role
    db.commit()


@router.post("/login")
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)) -> TokenResponse:
    username = payload.username.strip()
    rate_limiter.check(_rate_key("login", request_ip(request), username), limit=5, window_seconds=60)
    user = _find_user_by_username(db, username)

    if user is None or not verify_password(payload.password, user.password_hash):
        write_audit_log(
            db,
            action="login_failure",
            actor_username=username,
            target_type="user",
            target_id=username,
            request=request,
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")

    rate_limiter.clear(_rate_key("login", request_ip(request), username))
    write_audit_log(db, action="login_success", actor=user, target_type="user", target_id=user.id, request=request)
    token, expires_at = create_token(user)
    return TokenResponse(access_token=token, role=user.role, expires_at=expires_at)


@router.post("/register")
def register(payload: RegistrationRequest, request: Request, db: Session = Depends(get_db)) -> TokenResponse:
    username = payload.username.strip()
    rate_limiter.check(_rate_key("register", request_ip(request)), limit=5, window_seconds=3600)
    if not username or len(username) > 80:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username must be between 1 and 80 characters.")
    try:
        validate_password_policy(payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if _find_user_by_username(db, username) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username is already registered.")
    user = User(username=username, password_hash=hash_password(payload.password), role="viewer")
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username is already registered.") from exc
    db.refresh(user)
    write_audit_log(db, action="user_registered", actor=user, target_type="user", target_id=user.id, request=request, metadata={"plan_code": "free"})
    token, expires_at = create_token(user)
    return TokenResponse(access_token=token, role=user.role, expires_at=expires_at)


@admin_router.get("/admin/users", response_model=list[UserResponse])
def list_users(_admin: User = Depends(require_admin), db: Session = Depends(get_db)) -> list[UserResponse]:
    return [_user_response(user) for user in db.query(User).order_by(User.username).all()]


@admin_router.post("/admin/users/create", response_model=UserResponse)
def create_admin_user(
    payload: CreateUserRequest,
    request: Request,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> UserResponse:
    rate_limiter.check(_rate_key("create_user", admin.id), limit=10, window_seconds=3600)
    username = payload.username.strip()
    role = payload.role.strip().lower()
    if not username:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username is required.")
    if role not in ALL_ROLES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid role.")
    try:
        validate_password_policy(payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    user = User(username=username, password_hash=hash_password(payload.password), role=role)
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        write_audit_log(db, action="admin_action_failed", actor=admin, target_type="user", target_id=username, request=request)
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User already exists.") from exc
    db.refresh(user)
    write_audit_log(db, action="user_created", actor=admin, target_type="user", target_id=user.id, request=request, metadata={"role": role})
    return _user_response(user)


@admin_router.post("/admin/users/{user_id}/reset-password", response_model=UserResponse)
def reset_password(
    user_id: int,
    payload: ResetPasswordRequest,
    request: Request,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> UserResponse:
    rate_limiter.check(_rate_key("reset_password", user_id), limit=5, window_seconds=3600)
    try:
        validate_password_policy(payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    user = _find_user_by_id(db, user_id)
    user.password_hash = hash_password(payload.password)
    db.commit()
    write_audit_log(db, action="password_reset", actor=admin, target_type="user", target_id=user.id, request=request)
    return _user_response(user)


@admin_router.post("/admin/users/{user_id}/change-password", response_model=UserResponse)
def change_password(
    user_id: int,
    payload: ChangePasswordRequest,
    request: Request,
    actor: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> UserResponse:
    user = _find_user_by_id(db, user_id)
    if actor.role != "admin" and actor.id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Users can only change their own password.")
    if actor.role != "admin" and not payload.old_password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is required.")
    if actor.role != "admin" and not verify_password(payload.old_password or "", user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Current password is incorrect.")
    try:
        validate_password_policy(payload.new_password)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    user.password_hash = hash_password(payload.new_password)
    db.commit()
    write_audit_log(db, action="password_changed", actor=actor, target_type="user", target_id=user.id, request=request)
    return _user_response(user)


@admin_router.delete("/admin/users/{user_id}", response_model=UserResponse)
def delete_user(
    user_id: int,
    request: Request,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> UserResponse:
    user = _find_user_by_id(db, user_id)
    if user.id == admin.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Admins cannot delete their own account.")
    response = _user_response(user)
    db.delete(user)
    db.commit()
    write_audit_log(db, action="user_deleted", actor=admin, target_type="user", target_id=user_id, request=request)
    return response


# Backward-compatible endpoint for the existing topbar form.
@router.post("/users", response_model=UserResponse)
def create_user_alias(
    payload: CreateUserRequest,
    request: Request,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> UserResponse:
    return create_admin_user(payload, request, admin, db)


router.include_router(admin_router)
