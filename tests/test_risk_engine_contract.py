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
    assert result.warnings == []


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


def test_risk_engine_blocks_duplicate_and_weak_risk_reward():
    result = RiskEngine(RiskLimits(min_risk_reward=2.0)).validate(
        _signal(target_price=106.0),
        {
            "trades_today": 0,
            "daily_pnl": 0,
            "capital_per_trade": 10000,
            "open_positions": 0,
            "market_data_age_seconds": 5,
            "vix": 14,
            "kill_switch_active": False,
            "active_trade_keys": ["NIFTY:BUY:TEST"],
        },
    )

    assert result.allowed is False
    assert "DUPLICATE_TRADE" in result.blocked_by
    assert "RISK_REWARD_TOO_LOW" in result.blocked_by


def test_risk_engine_warns_on_expiry_and_volatility_zone():
    result = RiskEngine().validate(
        _signal(),
        {
            "trades_today": 0,
            "daily_pnl": 0,
            "capital_per_trade": 10000,
            "open_positions": 0,
            "market_data_age_seconds": 75,
            "vix": 19,
            "kill_switch_active": False,
            "expiry_day": True,
        },
    )

    assert result.allowed is True
    assert result.blocked_by == []
    assert len(result.warnings) == 3
    assert result.risk_score < 100


def test_risk_engine_blocks_low_liquidity_options_entry():
    result = RiskEngine().validate(
        _signal(),
        {
            "trades_today": 0,
            "daily_pnl": 0,
            "capital_per_trade": 10000,
            "open_positions": 0,
            "market_data_age_seconds": 5,
            "vix": 14,
            "kill_switch_active": False,
            "liquidity_status": "LOW",
        },
    )

    assert result.allowed is False
    assert "LOW_LIQUIDITY" in result.blocked_by
    assert any("Liquidity" in reason for reason in result.reasons)
    assert any("liquidity" in warning.lower() for warning in result.warnings)


def test_risk_engine_can_warn_without_blocking_low_liquidity():
    result = RiskEngine(RiskLimits(block_low_liquidity=False)).validate(
        _signal(),
        {
            "trades_today": 0,
            "daily_pnl": 0,
            "capital_per_trade": 10000,
            "open_positions": 0,
            "market_data_age_seconds": 5,
            "vix": 14,
            "kill_switch_active": False,
            "option_liquidity": "THIN",
        },
    )

    assert result.allowed is True
    assert result.blocked_by == []
    assert any("liquidity" in warning.lower() for warning in result.warnings)


def test_risk_engine_blocks_options_execution_hazards():
    result = RiskEngine(RiskLimits(block_expiry_day_option_buying=True)).validate(
        _signal(metadata={"instrument_type": "CE"}),
        {
            "trades_today": 0,
            "daily_pnl": 0,
            "capital_per_trade": 10000,
            "open_positions": 0,
            "market_data_age_seconds": 5,
            "vix": 14,
            "kill_switch_active": False,
            "slippage_bps": 30,
            "spread_bps": 50,
            "gap_pct": 1.2,
            "expiry_day": True,
            "gamma": 0.12,
            "broker_connected": False,
        },
    )

    assert result.allowed is False
    assert "SLIPPAGE_TOO_HIGH" in result.blocked_by
    assert "SPREAD_TOO_WIDE" in result.blocked_by
    assert "GAP_RISK" in result.blocked_by
    assert "EXPIRY_DECAY_RISK" in result.blocked_by
    assert "GAMMA_RISK" in result.blocked_by
    assert "BROKER_DISCONNECTED" in result.blocked_by


def test_risk_engine_blocks_news_and_holiday_risk():
    result = RiskEngine().validate(
        _signal(),
        {
            "trades_today": 0,
            "daily_pnl": 0,
            "capital_per_trade": 10000,
            "open_positions": 0,
            "market_data_age_seconds": 5,
            "vix": 14,
            "kill_switch_active": False,
            "news_impact": "HIGH",
            "market_session": "HOLIDAY",
        },
    )

    assert result.allowed is False
    assert "NEWS_RISK" in result.blocked_by
    assert "HOLIDAY_RISK" in result.blocked_by
    assert any("news" in warning.lower() for warning in result.warnings)
    assert any("holiday" in warning.lower() for warning in result.warnings)
