from __future__ import annotations

from fastapi.testclient import TestClient


def test_default_credentials_are_not_seeded_without_explicit_env(tmp_path, monkeypatch):
    from conftest import TEST_SECRET, reset_backend_modules

    monkeypatch.setenv("QUANTGRID_ENV", "local")
    monkeypatch.setenv("QUANTGRID_ALLOW_DEV_SEED_USERS", "true")
    monkeypatch.setenv("QUANTGRID_AUTH_SECRET", TEST_SECRET)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'quantgrid.sqlite3'}")
    monkeypatch.delenv("QUANTGRID_USERS", raising=False)
    reset_backend_modules()

    from Backend.presentation.api.main import app

    with TestClient(app) as client:
        response = client.post("/auth/login", json={"username": "admin", "password": "admin123"})

    assert response.status_code == 401
