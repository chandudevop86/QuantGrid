from __future__ import annotations

from datetime import datetime, timedelta, timezone

from Backend.application.signal_validation import candle_freshness, diagnose_signal_run
from Backend.presentation.api.trading_api import list_strategies


def test_candle_freshness_reports_recent_latest_candle():
    latest = datetime.now(timezone.utc) - timedelta(seconds=30)

    context = candle_freshness([
        {
            "timestamp": latest.isoformat(),
            "open": 1,
            "high": 2,
            "low": 1,
            "close": 2,
        }
    ])

    assert context["is_recent"] is True
    assert context["latest_candle_at"] == latest.isoformat()
    assert context["latest_candle_age_seconds"] <= 35
    assert context["max_candle_age_seconds"] == 300


def test_diagnostics_include_stale_candle_age():
    stale = datetime.now(timezone.utc) - timedelta(minutes=12)

    diagnostics = diagnose_signal_run(
        [],
        symbol="NIFTY",
        candle_source="yahoo-finance",
        candles=[
            {
                "timestamp": stale.isoformat(),
                "open": 1,
                "high": 2,
                "low": 1,
                "close": 2,
            }
        ],
    )

    assert "age" in diagnostics[0]
    assert "limit 300s" in diagnostics[0]


def test_strategy_list_route_creates_service():
    strategies = list_strategies()

    assert "amd" in strategies
