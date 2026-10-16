"""Regression coverage for SMC correctness and percentage-based risk sizing."""
from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from Backend.domain.models.signal import StrategySignal
from Backend.domain.strategies.base import risk_fraction
from Backend.domain.strategies.mtfa.trigger_detector import TriggerDetector
from Backend.domain.strategies.mtfa.zone_detector import ZoneDetector
from Backend.domain.strategies.mtfa.risk_manager import MTFARiskManager
from Backend.domain.smc.fvg import FVGDetector
from Backend.application.trade_qualification_engine import TradeQualificationEngine
from Backend.trading_system.risk import GlobalRiskManager


def _signal() -> StrategySignal:
    return StrategySignal(
        strategy_name="MTFA",
        symbol="NIFTY",
        side="BUY",
        entry_price=100,
        stop_loss=90,
        target_price=120,
        signal_time=datetime(2026, 10, 16, tzinfo=timezone.utc),
        metadata={"score": 9, "risk_pct": 0.5},
    )


def test_fractional_percentage_is_not_interpreted_as_50_percent():
    assert risk_fraction(0.5) == 0.005
    assert risk_fraction(1) == 0.01
    assert risk_fraction(0.1) == 0.001
    manager = GlobalRiskManager()
    quantity, budget, distance = manager.position_size(
        capital=100_000, risk_pct=0.5, entry=100, stop_loss=90, lot_size=1
    )
    assert (quantity, budget, distance) == (50, 500, 10)
    assert manager._risk_fraction(0.5) == 0.005


def test_fractional_percentage_consistent_in_trade_qualification():
    sizing = TradeQualificationEngine._position_size(_signal(), 100_000, 0.5)
    assert sizing.risk_amount == 500
    assert sizing.position_size == 50


def test_fractional_percentage_consistent_in_mtfa_risk_manager():
    from Backend.domain.strategies.mtfa.zone_detector import MTFAZone

    candles = pd.DataFrame({
        "close": [100.0] * 9,
        "high": [102.0] * 9,
        "low": [98.0] * 9,
        "atr_14": [2.0] * 9,
    })
    plan = MTFARiskManager().build(
        candles, 8, "BUY",
        MTFAZone("resistance", high=110.0, low=108.0, strength=2.0),
        capital=100_000, risk_pct=0.5,
    )
    assert plan.risk_amount == 500


def test_midpoint_cross_is_not_choch_without_protected_pivots():
    window = pd.DataFrame({
        "open": [100.0] * 20,
        "high": [101.0] * 20,
        "low": [99.0] * 20,
        "close": [100.0] * 20,
    })
    row = pd.Series({"open": 99.0, "close": 102.0})
    assert not TriggerDetector._choch(row, window, "BUY")


def test_order_block_requires_opposite_candle_and_structure_break():
    base = [
        {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.2}
        for _ in range(10)
    ]
    origin = {"open": 101.0, "high": 101.5, "low": 99.5, "close": 100.0}
    impulse = {"open": 100.0, "high": 111.0, "low": 99.5, "close": 110.0}
    rows = pd.DataFrame([*base, origin, impulse])
    block = ZoneDetector._order_block(rows, atr=2.0, side="BUY")
    assert block is not None and block.direction == "BUY"
    assert block.low == 99.5 and block.high == 101.5
    weak = pd.DataFrame([*base, origin, {"open": 100.0, "high": 101.0, "low": 99.5, "close": 100.4}])
    assert ZoneDetector._order_block(weak, atr=2.0, side="BUY") is None


def test_fully_filled_fvg_is_not_reported_as_active():
    rows = pd.DataFrame([
        {"open": 100, "high": 101, "low": 99, "close": 100},
        {"open": 102, "high": 103, "low": 101, "close": 103},
        {"open": 105, "high": 106, "low": 104, "close": 105},
        {"open": 103, "high": 105, "low": 100, "close": 101},
        {"open": 104, "high": 105, "low": 103, "close": 104},
    ])
    rows["atr_14"] = 2.0
    assert ZoneDetector._fair_value_gap(rows, atr=2.0, side="BUY") is None
    assert FVGDetector().find_active_return(rows, 4, "BUY", after_index=0) is None
