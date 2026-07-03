from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVICE_ROOT = ROOT / "services" / "trading-service"
sys.path.insert(0, str(SERVICE_ROOT))

from Backend.application.risk_engine import RiskEngine, RiskLimits
from Backend.domain.models.signal import StrategySignal


def _signal(**overrides) -> StrategySignal:
    data = {
        "strategy_name": "test",
        "symbol": "NIFTY",
        "side": "BUY",
        "entry_price": 100.0,
        "stop_loss": 95.0,
        "target_price": 110.0,
        "signal_time": datetime(2026, 7, 3, 9, 30, tzinfo=timezone.utc),
        "metadata": {},
    }
    data.update(overrides)
    return StrategySignal(**data)


def test_risk_engine_allows_clean_signal():
    result = RiskEngine().validate(
        _signal(),
        {
            "trades_today": 0,
            "daily_pnl": 0,
            "capital_per_trade": 10000,
            "open_positions": 0,
            "market_data_age_seconds": 10,
            "vix": 14,
            "kill_switch_active": False,
        },
    )

    assert result.allowed is True
    assert result.reasons == ["OK"]
    assert result.blocked_by == []
    assert result.risk_score == 100


def test_risk_engine_returns_blockers_and_score():
    result = RiskEngine(RiskLimits(max_trades_per_day=1, stale_market_data_seconds=60)).validate(
        _signal(stop_loss=0),
        {
            "trades_today": 1,
            "daily_pnl": -100,
            "capital_per_trade": 10000,
            "open_positions": 0,
            "market_data_age_seconds": 120,
            "vix": 14,
            "kill_switch_active": False,
        },
    )

    assert result.allowed is False
    assert "MAX_TRADES_PER_DAY" in result.blocked_by
    assert "STOP_LOSS_REQUIRED" in result.blocked_by
    assert "STALE_MARKET_DATA" in result.blocked_by
    assert result.risk_score < 100
