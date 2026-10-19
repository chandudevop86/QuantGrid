"""Regression checks for risk P&L used by order-entry gates."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import importlib
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from Backend.application import paper_trade_store


def _fixed_session_time():
    now = datetime.now(timezone.utc)
    today_ist = now.astimezone(ZoneInfo("Asia/Kolkata")).date()
    # Closed records are assigned to the active Indian trading session.
    return datetime(today_ist.year, today_ist.month, today_ist.day, 9, 30,
                    tzinfo=ZoneInfo("Asia/Kolkata")).astimezone(timezone.utc)


def _mock_risk_sources(monkeypatch, trades, open_positions, closed_positions):
    # Other API tests deliberately reset Backend.* modules between fixtures.
    # Resolve the modules that risk_status() will import at call time instead
    # of patching a potentially stale module object captured during collection.
    resolved_position_store = importlib.import_module("Backend.application.position_store")
    resolved_config = importlib.import_module("Backend.core.config")

    monkeypatch.setattr(paper_trade_store, "init_paper_trade_store", lambda: None)
    monkeypatch.setattr(paper_trade_store, "list_paper_trades", lambda limit: trades)
    monkeypatch.setattr(resolved_position_store, "list_open_positions", lambda **kwargs: open_positions)
    monkeypatch.setattr(resolved_position_store, "list_closed_positions", lambda limit: closed_positions)
    monkeypatch.setattr(resolved_position_store, "position_summary", lambda: {
        "open_positions": len(open_positions),
        "current_exposure": 200,
        "realized_pnl": -100,
    })
    monkeypatch.setattr(resolved_config, "get_settings", lambda: SimpleNamespace(
        capital=100000, risk_per_trade_pct=1, max_daily_loss=3000,
        risk_configured=True,
    ))


def test_mirrored_paper_close_is_counted_once_with_net_costs(monkeypatch):
    closed_at = _fixed_session_time()
    _mock_risk_sources(
        monkeypatch,
        trades=[
            {
                "status": "closed", "broker_order_id": "BROKER-1",
                "pnl": -120, "created_at": (closed_at - timedelta(days=2)).isoformat(),
            },
            {
                "status": "closed", "broker_order_id": None,
                "pnl": -30, "created_at": closed_at.isoformat(),
            },
        ],
        open_positions=[{"open_pnl": -20, "execution_mode": "paper"}],
        closed_positions=[
            {
                "broker_order_id": "BROKER-1", "closed_pnl": -100,
                "closed_at": closed_at.isoformat(), "execution_mode": "paper",
            }
        ],
    )
    status = paper_trade_store.risk_status()
    # -120 net mirrored trade + -30 standalone trade + -20 open; NEVER
    # add the mirrored position's -100 gross P&L a second time.
    assert status["daily_pnl"] == -170
    assert status["weekly_pnl"] == -170
    assert status["unrealized_pnl"] == -20


def test_live_position_is_counted_without_paper_trade_entry(monkeypatch):
    timestamp = _fixed_session_time()
    _mock_risk_sources(
        monkeypatch,
        trades=[],
        open_positions=[
            {"open_pnl": -12, "execution_mode": "live",
             "opened_at": timestamp.isoformat()}
        ],
        closed_positions=[],
    )
    status = paper_trade_store.risk_status()
    assert status["daily_pnl"] == -12
    assert status["trades_today"] == 1


def test_same_trade_created_previous_day_but_closed_today(monkeypatch):
    close = _fixed_session_time()
    _mock_risk_sources(
        monkeypatch,
        trades=[
            {"status": "closed", "broker_order_id": "OLDER-ENTRY",
             "pnl": -45, "created_at": (close - timedelta(days=3)).isoformat()}
        ],
        open_positions=[],
        closed_positions=[
            {"broker_order_id": "OLDER-ENTRY", "closed_pnl": -40,
             "closed_at": close.isoformat(), "execution_mode": "paper"}
        ],
    )
    assert paper_trade_store.risk_status()["daily_pnl"] == -45
