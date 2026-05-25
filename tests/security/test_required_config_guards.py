from __future__ import annotations

import pytest


def test_weak_auth_secret_rejected(monkeypatch):
    from Backend.core import config

    monkeypatch.setattr(config, "ENV_FILE_LOADED", True)
    monkeypatch.setenv("QUANTGRID_ENV", "production")
    monkeypatch.setenv("QUANTGRID_AUTH_SECRET", "short")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://user:pass@localhost/db")

    with pytest.raises(RuntimeError, match="at least 32 characters"):
        config.get_settings()


def test_sqlite_rejected_in_production(monkeypatch):
    from Backend.core import config

    monkeypatch.setattr(config, "ENV_FILE_LOADED", True)
    monkeypatch.setenv("QUANTGRID_ENV", "production")
    monkeypatch.setenv("QUANTGRID_AUTH_SECRET", "production-secret-that-is-long-enough-12345")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///prod.sqlite3")

    with pytest.raises(RuntimeError, match="SQLite is not allowed"):
        config.validate_security_config()
