from __future__ import annotations

from Backend.presentation.api.auth import current_user, require_roles, require_trade_execute

Role = str

__all__ = ["Role", "current_user", "require_roles", "require_trade_execute"]
