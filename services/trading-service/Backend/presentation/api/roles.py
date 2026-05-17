from __future__ import annotations

from fastapi import Header, HTTPException, status

Role = str

ALL_ROLES = {"admin", "trader", "analyst", "viewer", "ops"}


def current_role(x_quantgrid_role: str | None = Header(default=None)) -> Role:
    role = (x_quantgrid_role or "viewer").strip().lower()
    return role if role in ALL_ROLES else "viewer"


def require_roles(*allowed_roles: Role):
    allowed = set(allowed_roles)

    def dependency(role: Role = Header(default="viewer", alias="X-QuantGrid-Role")) -> Role:
        normalized = role.strip().lower()
        if normalized not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This role is not allowed to perform this action.",
            )
        return normalized

    return dependency
