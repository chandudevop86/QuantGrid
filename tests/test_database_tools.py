from __future__ import annotations

from Backend.tools.check_database import _mask_database_url
from test_sqlalchemy_trading_stores import reset_backend_modules


def test_mask_database_url_hides_password():
    masked = _mask_database_url("postgresql+psycopg://quant:secret@localhost:5432/quantgrid")

    assert masked == "postgresql+psycopg://quant:***@localhost:5432/quantgrid"
    assert "secret" not in masked


def test_mask_database_url_leaves_passwordless_url():
    url = "sqlite:///./Backend/data/quantgrid.sqlite3"

    assert _mask_database_url(url) == url


def test_check_database_initializes_trading_store_tables(monkeypatch):
    monkeypatch.setenv("QUANTGRID_ENV", "test")
    monkeypatch.setenv("QUANTGRID_AUTH_SECRET", "test-secret-value-that-is-long-enough-12345")
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    reset_backend_modules()

    from sqlalchemy import inspect
    from Backend.core.database import engine
    from Backend.tools.check_database import initialize_trading_database

    initialize_trading_database()

    tables = set(inspect(engine).get_table_names())
    assert {
        "jobs",
        "market_price_ticks",
        "market_candles",
        "paper_trades",
        "positions",
        "orders",
        "risk_state",
        "audit_logs",
    }.issubset(tables)
