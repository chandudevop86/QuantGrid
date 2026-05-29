from __future__ import annotations

from Backend.core.config import get_settings


def use_legacy_sqlite_store() -> bool:
    return get_settings().environment == "local"
