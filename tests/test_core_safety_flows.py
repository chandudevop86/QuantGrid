from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from conftest import admin_headers, reset_backend_modules

from Backend.application.candle_validation import CandleValidationSettings, validate_live_candle
from Backend.domain.models.signal import StrategySignal


IST = ZoneInfo("Asia/Kolkata")


def _candle_at(timestamp: datetime) -> dict:
    return {
        "timestamp": timestamp.isoformat(),
        "open": 100,
        "high": 102,
        "low": 99,
        "close": 101,
        "volume": 1000,
    }


def _execution_signal() -> StrategySignal:
    return StrategySignal(
        strategy_name="AMD + FVG + Supply/Demand",
        symbol="NIFTY",
        side="BUY",
        entry_price=103,
        stop_loss=100,
        target_price=110,
        signal_time=datetime.fromisoformat("2026-05-22T10:00:00+05:30"),
        metadata={"score": 9, "quantity": 75},
    )


def test_fresh_candle_validation_passes_for_live_market():
    now = datetime(2026, 5, 22, 10, 0, tzinfo=IST)
    result = validate_live_candle(
        [_candle_at(now - timedelta(seconds=45))],
        interval="1m",
        now=now,
        settings=CandleValidationSettings(reject_after_seconds=300, delayed_feed_tolerance_seconds=60),
    )

    assert result.valid is True
    assert result.valid_for_analysis is True
    assert result.valid_for_execution is True
    assert result.market_status == "LIVE MARKET"


def test_stale_candle_is_rejected_with_stale_reason():
    now = datetime(2026, 5, 22, 10, 0, tzinfo=IST)
    result = validate_live_candle(
        [_candle_at(now - timedelta(minutes=8))],
        interval="1m",
        now=now,
        settings=CandleValidationSettings(reject_after_seconds=300, delayed_feed_tolerance_seconds=60),
    )

    assert result.valid is False
    assert result.valid_for_execution is False
    assert result.market_status == "DELAYED FEED"
    assert any("stale during live market" in item for item in result.diagnostics)


def test_market_closed_allows_analysis_but_blocks_execution():
    now = datetime(2026, 5, 22, 16, 5, tzinfo=IST)
    latest = datetime(2026, 5, 22, 15, 30, tzinfo=IST)
    result = validate_live_candle([_candle_at(latest)], interval="1m", now=now)

    assert result.valid is True
    assert result.valid_for_analysis is True
    assert result.valid_for_execution is False
    assert result.market_status == "MARKET CLOSED"


def test_auto_paper_creates_order_only_for_valid_signal(app_client, monkeypatch):
    import Backend.presentation.api.execution as execution_api
    from Backend.application.trading_service import TradingService

    monkeypatch.setattr(
        execution_api,
        "get_candles",
        lambda symbol, interval="1m", period="1d", limit=150: {
            "symbol": symbol,
            "interval": interval,
            "fetched_at": "2026-05-22T04:30:00+00:00",
            "candles": [_candle_at(datetime(2026, 5, 22, 10, 0, tzinfo=IST))],
        },
    )
    monkeypatch.setattr(TradingService, "run_strategy", lambda self, **kwargs: [_execution_signal()])
    monkeypatch.setattr(execution_api, "validate_signals", lambda raw, **kwargs: (raw, "live"))
    monkeypatch.setattr(execution_api, "diagnose_signal_run", lambda raw, **kwargs: ["validated"])
    monkeypatch.setattr(execution_api, "_market_aligned", lambda item: True)
    monkeypatch.setattr(
        execution_api,
        "validate_live_candle",
        lambda *args, **kwargs: SimpleNamespace(
            valid=True,
            valid_for_analysis=True,
            valid_for_execution=True,
            market_status="LIVE MARKET",
            model_dump=lambda: {
                "valid": True,
                "valid_for_analysis": True,
                "valid_for_execution": True,
                "market_status": "LIVE MARKET",
            },
        ),
    )
    monkeypatch.setattr(
        execution_api,
        "decide_signal",
        lambda item, **kwargs: SimpleNamespace(
            score=9,
            regime="TRENDING",
            to_dict=lambda: {"allowed": True, "status": "ACTIVE", "reason": "OK", "score": 9},
        ),
    )
    monkeypatch.setattr(execution_api, "evaluate_risk_gate", lambda decision: SimpleNamespace(allowed=True, reason="OK"))
    monkeypatch.setattr(
        execution_api,
        "validate_execution_constraints",
        lambda item: SimpleNamespace(
            accepted=True,
            reason="OK",
            quantity=75,
            lot_size=75,
            notional=7725,
            required_margin=7725,
        ),
    )

    response = app_client.post(
        "/execution/auto-paper",
        json={"symbol": "NIFTY", "strategies": ["amd"]},
        headers=admin_headers(app_client),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "paper_order_submitted"


def test_auto_paper_returns_no_trade_without_valid_signals(app_client, monkeypatch):
    import Backend.presentation.api.execution as execution_api
    from Backend.application.trading_service import TradingService

    monkeypatch.setattr(
        execution_api,
        "get_candles",
        lambda symbol, interval="1m", period="1d", limit=150: {
            "symbol": symbol,
            "interval": interval,
            "fetched_at": "2026-05-22T04:30:00+00:00",
            "candles": [_candle_at(datetime(2026, 5, 22, 10, 0, tzinfo=IST))],
        },
    )
    monkeypatch.setattr(TradingService, "run_strategy", lambda self, **kwargs: [])

    response = app_client.post(
        "/execution/auto-paper",
        json={"symbol": "NIFTY", "strategies": ["amd"]},
        headers=admin_headers(app_client),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "no_trade"


def test_live_order_is_blocked_when_live_trading_is_disabled(app_client):
    headers = admin_headers(app_client)
    headers["X-QuantGrid-Mode"] = "live"

    response = app_client.post(
        "/execution/order",
        json={
            "strategy_name": "manual",
            "symbol": "NIFTY",
            "side": "BUY",
            "entry_price": 22500,
            "stop_loss": 22450,
            "target_price": 22600,
            "signal_time": "2026-05-22T10:00:00+05:30",
            "metadata": {"quantity": 1},
        },
        headers=headers,
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Live trading is disabled. Paper trading only."


def test_weak_auth_secret_rejected_at_startup(monkeypatch):
    monkeypatch.setenv("QUANTGRID_ENV", "production")
    monkeypatch.setenv("QUANTGRID_AUTH_SECRET", "short")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://user:pass@localhost/db")
    reset_backend_modules()

    from Backend.core.config import get_settings

    with pytest.raises(RuntimeError, match="at least 32 characters"):
        get_settings()

    reset_backend_modules()


def test_sqlite_database_url_rejected_in_production(monkeypatch):
    monkeypatch.setenv("QUANTGRID_ENV", "production")
    monkeypatch.setenv("QUANTGRID_AUTH_SECRET", "production-secret-that-is-long-enough-12345")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///prod.sqlite3")
    reset_backend_modules()

    from Backend.core.config import validate_security_config

    with pytest.raises(RuntimeError, match="SQLite is not allowed"):
        validate_security_config()

    reset_backend_modules()
