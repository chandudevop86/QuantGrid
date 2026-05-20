from __future__ import annotations

import pytest


def test_auth_secret_required_in_production(monkeypatch):
    from conftest import reset_backend_modules

    monkeypatch.setenv("QUANTGRID_ENV", "production")
    monkeypatch.delenv("QUANTGRID_AUTH_SECRET", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://user:pass@localhost/db")
    reset_backend_modules()

    from Backend.core.config import get_settings

    with pytest.raises(RuntimeError, match="QUANTGRID_AUTH_SECRET"):
        get_settings()


def test_auth_secret_minimum_length(monkeypatch):
    from conftest import reset_backend_modules

    monkeypatch.setenv("QUANTGRID_ENV", "local")
    monkeypatch.setenv("QUANTGRID_AUTH_SECRET", "short")
    reset_backend_modules()

    from Backend.core.config import get_settings

    with pytest.raises(RuntimeError, match="at least 32"):
        get_settings()
