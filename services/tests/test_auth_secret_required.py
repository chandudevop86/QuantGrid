from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


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


def test_app_startup_fails_with_weak_auth_secret(tmp_path, monkeypatch):
    from conftest import reset_backend_modules

    monkeypatch.setenv("QUANTGRID_ENV", "local")
    monkeypatch.setenv("QUANTGRID_AUTH_SECRET", "short")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'quantgrid.sqlite3'}")
    monkeypatch.setenv("MARKET_DATA_DB_FILE", str(tmp_path / "market.sqlite3"))
    monkeypatch.setenv("JOB_STORE_DB_FILE", str(tmp_path / "jobs.sqlite3"))
    reset_backend_modules()

    with pytest.raises(RuntimeError, match="at least 32 characters"):
        from Backend.presentation.api.main import app  # noqa: F401

    reset_backend_modules()


def test_app_startup_fails_with_sqlite_in_production(monkeypatch):
    from conftest import reset_backend_modules

    monkeypatch.setenv("QUANTGRID_ENV", "production")
    monkeypatch.setenv("QUANTGRID_AUTH_SECRET", "production-secret-that-is-long-enough-12345")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///prod.sqlite3")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "https://quantgrid.example.com")
    reset_backend_modules()

    from Backend.presentation.api.main import app

    with pytest.raises(RuntimeError, match="SQLite is not allowed"):
        with TestClient(app):
            pass

    reset_backend_modules()


def test_settings_loads_env_file(tmp_path, monkeypatch):
    from conftest import reset_backend_modules

    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "QUANTGRID_ENV=local",
                "QUANTGRID_AUTH_SECRET='env-file-secret-that-is-long-enough-12345'",
                "QUANTGRID_USERS=admin:AdminPass1!:admin",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("QUANTGRID_ENV_FILE", str(env_file))
    monkeypatch.delenv("QUANTGRID_AUTH_SECRET", raising=False)
    reset_backend_modules()

    from Backend.core.config import get_settings

    settings = get_settings()

    assert settings.auth_secret == "env-file-secret-that-is-long-enough-12345"
    assert settings.bootstrap_users == "admin:AdminPass1!:admin"


def test_environment_overrides_env_file(tmp_path, monkeypatch):
    from conftest import reset_backend_modules

    env_file = tmp_path / ".env"
    env_file.write_text(
        "QUANTGRID_AUTH_SECRET=env-file-secret-that-is-long-enough-12345",
        encoding="utf-8",
    )
    monkeypatch.setenv("QUANTGRID_ENV_FILE", str(env_file))
    monkeypatch.setenv("QUANTGRID_AUTH_SECRET", "real-env-secret-that-is-long-enough-12345")
    reset_backend_modules()

    from Backend.core.config import get_settings

    assert get_settings().auth_secret == "real-env-secret-that-is-long-enough-12345"
