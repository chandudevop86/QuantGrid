from __future__ import annotations

import importlib
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVICE_ROOT = ROOT / "services" / "trading-service"
sys.path.insert(0, str(SERVICE_ROOT))


def reset_backend_modules() -> None:
    for name in list(sys.modules):
        if name == "Backend" or name.startswith("Backend."):
            del sys.modules[name]


def configure_sqlalchemy_store(monkeypatch) -> None:
    monkeypatch.setenv("QUANTGRID_ENV", "test")
    monkeypatch.setenv("QUANTGRID_AUTH_SECRET", "test-secret-value-that-is-long-enough-12345")
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    reset_backend_modules()


def test_sqlalchemy_job_store_interface(monkeypatch):
    configure_sqlalchemy_store(monkeypatch)
    from Backend.application import job_store

    job_store.init_job_store()
    created = job_store.create_job(
        {"job_id": "job-1", "status": "queued", "created_at": "2026-05-29T09:15:00+00:00"},
        {"strategy": "breakout"},
    )

    assert created["job_id"] == "job-1"
    assert job_store.count_jobs("queued") == 1
    claimed = job_store.claim_job("job-1")
    assert claimed is not None
    job, payload = claimed
    assert job["status"] == "running"
    assert payload["strategy"] == "breakout"


def test_sqlalchemy_market_trade_position_and_kill_switch_stores(monkeypatch):
    configure_sqlalchemy_store(monkeypatch)
    from Backend.application import kill_switch, market_data_store, paper_trade_store, position_store

    market_data_store.store_candles(
        symbol="NIFTY",
        market_symbol="^NSEI",
        interval="1m",
        source="test",
        candles=[
            {"timestamp": "2026-05-29T09:15:00+05:30", "open": 1, "high": 2, "low": 1, "close": 2, "volume": 100},
            {"timestamp": "2026-05-29T09:16:00+05:30", "open": 2, "high": 3, "low": 2, "close": 3, "volume": 120},
        ],
    )
    assert [item["close"] for item in market_data_store.latest_candles("NIFTY", "1m", 2)] == [2, 3]

    trade = paper_trade_store.create_paper_trade(
        {
            "strategy": "breakout",
            "symbol": "NIFTY",
            "side": "BUY",
            "entry": 100,
            "stop_loss": 95,
            "target": 110,
            "status": "paper_order_submitted",
            "broker_order_id": "BRK-1",
            "broker_status": "open",
            "raw_safe_broker_response": {"orderId": "BRK-1", "access-token": "secret"},
        }
    )
    assert trade["broker_order_id"] == "BRK-1"
    assert trade["broker_status"] == "open"
    assert trade["raw_safe_broker_response"]["orderId"] == "BRK-1"
    updated_trade = paper_trade_store.update_paper_trade_status(
        "BRK-1",
        status="broker_rejected",
        reason="test",
        broker_status="rejected",
        raw_safe_broker_response={"status": "REJECTED"},
    )
    assert updated_trade is not None
    assert updated_trade["status"] == "broker_rejected"
    assert updated_trade["broker_status"] == "rejected"
    assert updated_trade["raw_safe_broker_response"]["status"] == "REJECTED"

    position = position_store.create_open_position(
        {
            "broker_order_id": "BRK-1",
            "symbol": "NIFTY",
            "side": "BUY",
            "quantity": 50,
            "entry_price": 100,
            "stop_loss": 95,
            "target": 110,
        }
    )
    assert position_store.find_position_by_broker_order_id("BRK-1")["id"] == position["id"]
    closed = position_store.close_open_position(position["id"], current_price=105)
    assert closed is not None
    assert closed["status"] == "closed"
    assert closed["closed_pnl"] == 250

    assert kill_switch.kill_switch_status()["active"] is False
    assert kill_switch.activate_kill_switch(reason="test", actor="admin")["active"] is True
    assert kill_switch.deactivate_kill_switch(actor="admin")["active"] is False


def test_production_rejects_missing_or_sqlite_database(monkeypatch):
    monkeypatch.setenv("QUANTGRID_ENV", "production")
    monkeypatch.setenv("QUANTGRID_AUTH_SECRET", "test-secret-value-that-is-long-enough-12345")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    reset_backend_modules()
    config = importlib.import_module("Backend.core.config")

    try:
        config.validate_security_config()
    except RuntimeError as exc:
        assert "DATABASE_URL must be set" in str(exc)
    else:
        raise AssertionError("production must require DATABASE_URL")

    monkeypatch.setenv("DATABASE_URL", "sqlite:///prod.sqlite3")
    reset_backend_modules()
    config = importlib.import_module("Backend.core.config")
    try:
        config.validate_security_config()
    except RuntimeError as exc:
        assert "SQLite is not allowed" in str(exc)
    else:
        raise AssertionError("production must reject SQLite")


def test_local_ignores_container_only_postgres_host(monkeypatch):
    monkeypatch.setenv("QUANTGRID_ENV", "local")
    monkeypatch.setenv("QUANTGRID_AUTH_SECRET", "test-secret-value-that-is-long-enough-12345")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://quant:secret@postgres:5432/quantgrid")
    reset_backend_modules()
    config = importlib.import_module("Backend.core.config")

    settings = config.get_settings()

    assert settings.database_url.startswith("sqlite:///")


def test_production_keeps_container_postgres_url(monkeypatch):
    database_url = "postgresql+psycopg://quant:secret@postgres:5432/quantgrid"
    monkeypatch.setenv("QUANTGRID_ENV", "production")
    monkeypatch.setenv("QUANTGRID_AUTH_SECRET", "test-secret-value-that-is-long-enough-12345")
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("QUANTGRID_MARKET_DATA_PROVIDER", "dhan")
    reset_backend_modules()
    config = importlib.import_module("Backend.core.config")

    settings = config.validate_security_config()

    assert settings.database_url == database_url
