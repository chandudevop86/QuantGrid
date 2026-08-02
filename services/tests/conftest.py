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


@pytest.fixture(autouse=True)
def clear_process_caches_between_tests():
    module = sys.modules.get("Backend.core.config")
    if module is not None and hasattr(module, "_cached_settings"):
        module._cached_settings.cache_clear()
    kill_switch = sys.modules.get("Backend.application.kill_switch")
    if kill_switch is not None and hasattr(kill_switch, "_invalidate_cache"):
        kill_switch._invalidate_cache()
    yield
    module = sys.modules.get("Backend.core.config")
    if module is not None and hasattr(module, "_cached_settings"):
        module._cached_settings.cache_clear()
    kill_switch = sys.modules.get("Backend.application.kill_switch")
    if kill_switch is not None and hasattr(kill_switch, "_invalidate_cache"):
        kill_switch._invalidate_cache()

@pytest.fixture()
def app_client(tmp_path, monkeypatch):
    monkeypatch.setenv("QUANTGRID_ENV", "local")
    monkeypatch.setenv("QUANTGRID_ALLOW_DEV_SEED_USERS", "true")
    monkeypatch.setenv("QUANTGRID_AUTH_SECRET", TEST_SECRET)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'quantgrid.sqlite3'}")
    monkeypatch.setenv("MARKET_DATA_DB_FILE", str(tmp_path / "market.sqlite3"))
    monkeypatch.setenv("JOB_STORE_DB_FILE", str(tmp_path / "jobs.sqlite3"))
    monkeypatch.setenv("BACKTEST_JOB_STORE_DB_FILE", str(tmp_path / "backtest_jobs.sqlite3"))
    monkeypatch.setenv("PAPER_TRADE_DB_FILE", str(tmp_path / "paper_trades.sqlite3"))
    monkeypatch.setenv("POSITION_STORE_DB_FILE", str(tmp_path / "positions.sqlite3"))
    monkeypatch.setenv("KILL_SWITCH_DB_FILE", str(tmp_path / "risk_state.sqlite3"))
    monkeypatch.setenv("STRATEGY_GOVERNANCE_DB_FILE", str(tmp_path / "strategy_governance.sqlite3"))
    monkeypatch.setenv("QUANTGRID_USERS", f"admin:{TEST_ADMIN_PASSWORD}:admin")
    monkeypatch.delenv("QUANTGRID_ENABLE_LIVE_TRADING", raising=False)
    reset_backend_modules()

    from Backend.application.kill_switch import deactivate_kill_switch
    from Backend.presentation.api.main import app

    deactivate_kill_switch(actor="test-fixture")

    with TestClient(app) as client:
        yield client

    reset_backend_modules()


def admin_headers(client: TestClient) -> dict[str, str]:
    response = client.post("/auth/login", json={"username": "admin", "password": TEST_ADMIN_PASSWORD})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}

