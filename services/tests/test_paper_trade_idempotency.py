from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import inspect, text


ROOT = Path(__file__).resolve().parents[2]
SERVICE_ROOT = ROOT / "services" / "trading-service"
sys.path.insert(0, str(SERVICE_ROOT))


def _reset_backend_modules() -> None:
    for name in list(sys.modules):
        if name == "Backend" or name.startswith("Backend."):
            del sys.modules[name]


def _configure_sqlalchemy_store(monkeypatch) -> None:
    monkeypatch.setenv("QUANTGRID_ENV", "ci")
    monkeypatch.setenv(
        "QUANTGRID_AUTH_SECRET",
        "test-secret-value-that-is-long-enough-12345",
    )
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    _reset_backend_modules()

    from Backend.core.database import init_database

    init_database()


def test_same_strategy_symbol_and_signal_time_is_idempotent(monkeypatch):
    _configure_sqlalchemy_store(monkeypatch)

    from Backend.application import paper_trade_store
    from Backend.core.database import engine

    payload = {
        "strategy": "breakout",
        "symbol": "NIFTY",
        "side": "BUY",
        "entry": 22800,
        "stop_loss": 22750,
        "target": 22900,
        "status": "paper_simulated",
        "signal_time": "2026-09-28T10:00:00+00:00",
    }

    first = paper_trade_store.create_paper_trade(payload)
    second = paper_trade_store.create_paper_trade(payload)

    assert second["id"] == first["id"]

    with engine.connect() as connection:
        trade_count = connection.execute(
            text(
                """
                SELECT COUNT(*)
                FROM paper_trades
                WHERE strategy = 'breakout'
                  AND symbol = 'NIFTY'
                  AND signal_time = '2026-09-28 10:00:00.000000'
                """
            )
        ).scalar_one()
        journal_count = connection.execute(
            text(
                """
                SELECT COUNT(*)
                FROM trade_journal
                WHERE strategy = 'breakout'
                  AND symbol = 'NIFTY'
                  AND source = 'paper_trade'
                """
            )
        ).scalar_one()

    assert trade_count == 1
    assert journal_count == 1


def test_signal_identity_unique_index_is_installed(monkeypatch):
    _configure_sqlalchemy_store(monkeypatch)

    from Backend.core.database import engine

    indexes = inspect(engine).get_indexes("paper_trades")
    identity = next(
        index
        for index in indexes
        if index["name"] == "uq_paper_trades_signal_identity"
    )

    assert bool(identity["unique"]) is True
    assert identity["column_names"] == ["strategy", "symbol", "signal_time"]


def test_different_signal_times_create_distinct_paper_trades(monkeypatch):
    _configure_sqlalchemy_store(monkeypatch)

    from Backend.application import paper_trade_store

    base = {
        "strategy": "breakout",
        "symbol": "NIFTY",
        "side": "BUY",
        "entry": 22800,
        "stop_loss": 22750,
        "target": 22900,
        "status": "paper_simulated",
    }

    first = paper_trade_store.create_paper_trade(
        {**base, "signal_time": "2026-09-28T10:00:00+00:00"}
    )
    second = paper_trade_store.create_paper_trade(
        {**base, "signal_time": "2026-09-28T10:01:00+00:00"}
    )

    assert second["id"] != first["id"]
