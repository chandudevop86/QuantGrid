from __future__ import annotations

from fastapi.testclient import TestClient

from conftest import TEST_SECRET, reset_backend_modules


def test_default_credentials_are_not_seeded_without_explicit_env(tmp_path, monkeypatch):
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


def test_bootstrap_user_updates_existing_local_seed_password(tmp_path, monkeypatch):
    monkeypatch.setenv("QUANTGRID_ENV", "local")
    monkeypatch.setenv("QUANTGRID_ALLOW_DEV_SEED_USERS", "true")
    monkeypatch.setenv("QUANTGRID_AUTH_SECRET", TEST_SECRET)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'quantgrid.sqlite3'}")
    monkeypatch.setenv("QUANTGRID_USERS", "admin:OldAdminPass1!:viewer")
    reset_backend_modules()

    from Backend.presentation.api.main import app

    with TestClient(app) as client:
        old_login = client.post("/auth/login", json={"username": "admin", "password": "OldAdminPass1!"})
        assert old_login.status_code == 200
        assert old_login.json()["role"] == "viewer"

    monkeypatch.setenv("QUANTGRID_USERS", "admin:AdminPass1!:admin")
    reset_backend_modules()

    from Backend.presentation.api.main import app as updated_app

    with TestClient(updated_app) as client:
        old_password = client.post("/auth/login", json={"username": "admin", "password": "OldAdminPass1!"})
        new_password = client.post("/auth/login", json={"username": "admin", "password": "AdminPass1!"})

    assert old_password.status_code == 401
    assert new_password.status_code == 200
    assert new_password.json()["role"] == "admin"
