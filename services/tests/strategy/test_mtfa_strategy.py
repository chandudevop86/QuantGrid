from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SERVICE_ROOT = ROOT / "services" / "trading-service"
sys.path.insert(0, str(SERVICE_ROOT))

from Backend.application.dto import serialize_signal
from Backend.domain.engine.strategy_engine import StrategyEngine
from Backend.domain.models.context import StrategyContext
from Backend.domain.strategies.mtfa import MTFAConfig, MTFAStrategy
from Backend.domain.strategies.mtfa.mtfa_validator import MTFAValidator


START = datetime(2026, 5, 29, 9, 15, tzinfo=timezone.utc)


def _candles(values: list[tuple[float, float, float, float, float]], minutes: int) -> list[dict]:
    return [
        {
            "timestamp": (START + timedelta(minutes=index * minutes)).isoformat(),
            "open": open_price,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        }
        for index, (open_price, high, low, close, volume) in enumerate(values)
    ]


def _h4_uptrend() -> list[dict]:
    values = []
    for index in range(16):
        open_price = 100 + index * 2
        close = open_price + 1.2
        values.append((open_price, close + 1.0, open_price - 0.8 + index * 0.3, close, 1000 + index * 50))
    return _candles(values, 240)


def _h4_downtrend() -> list[dict]:
    values = []
    for index in range(16):
        open_price = 132 - index * 2
        close = open_price - 1.2
        values.append((open_price, open_price + 0.8 - index * 0.2, close - 1.0, close, 1000 + index * 50))
    return _candles(values, 240)


def _h1_demand_pullback() -> list[dict]:
    values = [(108 - index, 109 - index, 104 - index, 105 - index, 1000) for index in range(8)]
    values.extend(
        [
            (101.5, 103.0, 99.5, 102.8, 1600),
            (102.5, 104.0, 101.8, 103.5, 1800),
        ]
    )
    return _candles(values, 60)


def _m15_bullish_trigger() -> list[dict]:
    values = [(102 + index * 0.1, 103 + index * 0.1, 101.5 + index * 0.1, 102.4 + index * 0.1, 1000 + index * 20) for index in range(10)]
    values.extend(
        [
            (103.0, 103.4, 100.8, 101.2, 1300),
            (101.1, 104.8, 100.9, 104.5, 2200),
        ]
    )
    return _candles(values, 15)


def test_mtfa_strategy_generates_aligned_buy_signal():
    strategy = MTFAStrategy(MTFAConfig(min_score=7))
    m15 = _m15_bullish_trigger()
    signals = strategy.run(
        m15,
        StrategyContext(
            symbol="NIFTY",
            capital=100000,
            risk_pct=1,
            rr_ratio=2,
            params={"h4_candles": _h4_uptrend(), "h1_candles": _h1_demand_pullback(), "m15_candles": m15},
        ),
    )

    assert signals
    signal = signals[-1]
    assert signal.strategy_name == "MTFA"
    assert signal.side == "BUY"
    assert signal.metadata["strategy_key"] == "mtfa"
    assert signal.metadata["mtfa_valid"] is True
    assert signal.metadata["mtfa_4h_trend"] == "UPTREND"
    assert signal.metadata["mtfa_4h_zone"]["zone_type"] in {"demand", "support"}
    assert signal.metadata["mtfa_15m_trigger"]["trigger_type"] in {"BOS", "ChoCH", "Buy Engulfing", "Liquidity Sweep", "False Breakout"}
    assert signal.metadata["risk_reward"] >= 2.0
    assert signal.metadata["quality_grade"] in {"A+", "A", "B"}


def test_mtfa_rejects_bullish_trigger_against_bearish_h4_context():
    strategy = MTFAStrategy(MTFAConfig(min_score=7))
    m15 = _m15_bullish_trigger()
    signals = strategy.run(
        m15,
        StrategyContext(
            symbol="NIFTY",
            capital=100000,
            risk_pct=1,
            rr_ratio=2,
            params={"h4_candles": _h4_downtrend(), "h1_candles": _h1_demand_pullback(), "m15_candles": m15},
        ),
    )

    assert not any(signal.side == "BUY" for signal in signals)


def test_mtfa_validator_rejects_low_rr_and_countertrend():
    validator = MTFAValidator()

    low_rr = validator.validate(
        trend_aligned=True,
        zone_touched=True,
        confirmation_score=2,
        trigger_valid=True,
        volume_confirmed=True,
        rr=1.5,
        countertrend=False,
    )
    countertrend = validator.validate(
        trend_aligned=True,
        zone_touched=True,
        confirmation_score=2,
        trigger_valid=True,
        volume_confirmed=False,
        rr=3.2,
        countertrend=True,
    )

    assert low_rr.valid is False
    assert "RR below 2" in low_rr.reasons
    assert countertrend.valid is False
    assert "countertrend rejected" in countertrend.reasons


def test_strategy_engine_and_serializer_expose_mtfa_fields():
    assert "mtfa" in StrategyEngine().available()

    strategy = MTFAStrategy(MTFAConfig(min_score=7))
    m15 = _m15_bullish_trigger()
    signal = strategy.run(
        m15,
        StrategyContext(
            symbol="NIFTY",
            capital=100000,
            risk_pct=1,
            rr_ratio=2,
            params={"h4_candles": _h4_uptrend(), "h1_candles": _h1_demand_pullback(), "m15_candles": m15},
        ),
    )[-1]

    payload = serialize_signal(signal)

    assert payload["mtfa_4h_trend"] == "UPTREND"
    assert payload["mtfa_4h_zone"]["zone_type"] in {"demand", "support"}
    assert payload["mtfa_1h_pullback"]["pullback_valid"] is True
    assert payload["mtfa_15m_trigger"]["valid"] is True
