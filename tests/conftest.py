from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
SERVICE_ROOT = ROOT / "services" / "trading-service"
sys.path.insert(0, str(SERVICE_ROOT))

TEST_SECRET = "test-secret-value-that-is-long-enough-12345"
TEST_ADMIN_PASSWORD = "AdminPass1!"


def reset_backend_modules() -> None:
    for name in list(sys.modules):
        if name == "Backend" or name.startswith("Backend."):
            del sys.modules[name]


@pytest.fixture()
def app_client(tmp_path, monkeypatch):
    monkeypatch.setenv("QUANTGRID_ENV", "local")
    monkeypatch.setenv("QUANTGRID_ALLOW_DEV_SEED_USERS", "true")
    monkeypatch.setenv("QUANTGRID_AUTH_SECRET", TEST_SECRET)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'quantgrid.sqlite3'}")
    monkeypatch.setenv("MARKET_DATA_DB_FILE", str(tmp_path / "market.sqlite3"))
    monkeypatch.setenv("JOB_STORE_DB_FILE", str(tmp_path / "jobs.sqlite3"))
    monkeypatch.setenv("QUANTGRID_USERS", f"admin:{TEST_ADMIN_PASSWORD}:admin")
    monkeypatch.delenv("QUANTGRID_ENABLE_LIVE_TRADING", raising=False)
    reset_backend_modules()

    from Backend.presentation.api.main import app

    with TestClient(app) as client:
        yield client

    reset_backend_modules()


def admin_headers(client: TestClient) -> dict[str, str]:
    response = client.post("/auth/login", json={"username": "admin", "password": TEST_ADMIN_PASSWORD})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}
