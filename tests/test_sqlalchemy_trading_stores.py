from __future__ import annotations

import importlib
import sys
from pathlib import Path

from sqlalchemy import inspect, text
from sqlalchemy.exc import OperationalError


ROOT = Path(__file__).resolve().parents[1]
SERVICE_ROOT = ROOT / "services" / "trading-service"
sys.path.insert(0, str(SERVICE_ROOT))


def reset_backend_modules() -> None:
    for name in list(sys.modules):
        if name == "Backend" or name.startswith("Backend."):
            del sys.modules[name]


def configure_sqlalchemy_store(monkeypatch) -> None:
    monkeypatch.setenv("QUANTGRID_ENV", "ci")
    monkeypatch.setenv("QUANTGRID_AUTH_SECRET", "test-secret-value-that-is-long-enough-12345")
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    reset_backend_modules()


def test_test_environment_uses_file_backed_local_stores(monkeypatch):
    monkeypatch.setenv("QUANTGRID_ENV", "test")
    monkeypatch.setenv("QUANTGRID_AUTH_SECRET", "test-secret-value-that-is-long-enough-12345")
    reset_backend_modules()

    from Backend.application.store_backend import use_legacy_sqlite_store

    assert use_legacy_sqlite_store() is True


def test_hot_path_stores_initialize_once_per_engine(monkeypatch):
    configure_sqlalchemy_store(monkeypatch)
    from Backend.application import job_store, market_data_store, paper_trade_store, position_store
    from Backend.core import database

    market_initializations = 0
    paper_initializations = 0
    job_initializations = 0
    position_initializations = 0

    def initialize_market_store():
        nonlocal market_initializations
        market_initializations += 1

    def initialize_paper_store():
        nonlocal paper_initializations
        paper_initializations += 1

    def initialize_job_store():
        nonlocal job_initializations
        job_initializations += 1

    def initialize_position_store():
        nonlocal position_initializations
        position_initializations += 1

    monkeypatch.setattr(market_data_store, "_initialize_market_data_store", initialize_market_store)
    monkeypatch.setattr(paper_trade_store, "_initialize_paper_trade_store", initialize_paper_store)
    monkeypatch.setattr(job_store, "_initialize_job_store", initialize_job_store)
    monkeypatch.setattr(position_store, "_initialize_position_store", initialize_position_store)

    market_data_store.init_market_data_store()
    market_data_store.init_market_data_store()
    paper_trade_store.init_paper_trade_store()
    paper_trade_store.init_paper_trade_store()
    job_store.init_job_store()
    job_store.init_job_store()
    position_store.init_position_store()
    position_store.init_position_store()

    assert market_initializations == 1
    assert paper_initializations == 1
    assert job_initializations == 1
    assert position_initializations == 1

    database._rebuild_engine("sqlite://")
    market_data_store.init_market_data_store()
    paper_trade_store.init_paper_trade_store()
    job_store.init_job_store()
    position_store.init_position_store()

    assert market_initializations == 2
    assert paper_initializations == 2
    assert job_initializations == 2
    assert position_initializations == 2


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


def test_sqlalchemy_position_store_migrates_pending_exit_columns(monkeypatch):
    configure_sqlalchemy_store(monkeypatch)
    from Backend.core.database import engine
    from Backend.application import position_store

    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE positions (
                    id INTEGER PRIMARY KEY,
                    broker_order_id VARCHAR(120),
                    symbol VARCHAR(32) NOT NULL,
                    side VARCHAR(10) NOT NULL,
                    quantity INTEGER NOT NULL,
                    entry_price FLOAT NOT NULL,
                    stop_loss FLOAT,
                    target FLOAT,
                    trailing_stop_loss FLOAT,
                    trailing_stop_pct FLOAT,
                    current_price FLOAT,
                    exit_price FLOAT,
                    exit_reason VARCHAR(80),
                    open_pnl FLOAT NOT NULL DEFAULT 0,
                    closed_pnl FLOAT NOT NULL DEFAULT 0,
                    status VARCHAR(20) NOT NULL,
                    opened_at VARCHAR(40) NOT NULL,
                    closed_at VARCHAR(40),
                    updated_at VARCHAR(40) NOT NULL
                )
                """
            )
        )

    position_store.init_position_store()
    columns = {column["name"] for column in inspect(engine).get_columns("positions")}

    assert "pending_exit_correlation_id" in columns
    assert "pending_exit_broker_order_id" in columns


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


def test_init_database_retries_postgres_service_name_on_localhost(monkeypatch):
    database_url = "postgresql+psycopg://quant:secret@postgres:5432/quantgrid"
    monkeypatch.setenv("QUANTGRID_ENV", "production")
    monkeypatch.setenv("QUANTGRID_AUTH_SECRET", "test-secret-value-that-is-long-enough-12345")
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("QUANTGRID_MARKET_DATA_PROVIDER", "dhan")
    reset_backend_modules()
    database = importlib.import_module("Backend.core.database")

    calls = []
    rebuilt_urls = []

    def fake_create_all(bind):
        calls.append(bind)
        if len(calls) == 1:
            raise OperationalError(None, None, Exception("failed to resolve host 'postgres'"))

    monkeypatch.setattr(database.Base.metadata, "create_all", fake_create_all)
    monkeypatch.setattr(database, "_rebuild_engine", rebuilt_urls.append)

    database.init_database()

    assert rebuilt_urls == ["postgresql+psycopg://quant:secret@127.0.0.1:5432/quantgrid"]
    assert len(calls) == 2
