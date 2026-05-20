from __future__ import annotations

from fastapi import Header, HTTPException, status

from Backend.presentation.api.auth import verify_token

Role = str

ALL_ROLES = {"admin", "trader", "analyst", "viewer", "ops"}


def current_role(authorization: str | None = Header(default=None)) -> Role:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
        )

    claims = verify_token(authorization.split(" ", 1)[1].strip())
    return str(claims["role"]).lower()


def require_roles(*allowed_roles: Role):
    allowed = set(allowed_roles)

    def dependency(role: Role = Header(default=None, alias="Authorization")) -> Role:
        normalized = current_role(role)
        if normalized not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This role is not allowed to perform this action.",
            )
        return normalized

    return dependency
