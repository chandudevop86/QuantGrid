from __future__ import annotations

from datetime import datetime, timedelta, timezone

from Backend.application.signal_validation import diagnose_signal_run, validate_signals
from Backend.domain.models.signal import StrategySignal
from Backend.domain.strategies.breakout import BreakoutConfig, run_breakout_strategy


def _breakout_candles() -> list[dict]:
    start = datetime(2026, 5, 22, 9, 15, tzinfo=timezone.utc)
    candles: list[dict] = []
    for index in range(60):
        if index < 30:
            open_price = 100 + (index % 4) * 0.1
            close = 100.2 + (index % 5) * 0.08
            high = 101.0
            low = 99.0
        elif index == 30:
            open_price = 100.5
            close = 101.8
            high = 102.0
            low = 100.4
        else:
            open_price = 101.8 + index * 0.05
            close = open_price + 0.2
            high = close + 0.3
            low = open_price - 0.2

        candles.append(
            {
                "timestamp": (start + timedelta(minutes=index)).isoformat(),
                "open": open_price,
                "high": high,
                "low": low,
                "close": close,
                "volume": 1000 + index * 100,
            }
        )
    return candles


def test_breakout_strategy_generates_raw_buy_or_sell_setups():
    signals = run_breakout_strategy(
        _breakout_candles(),
        symbol="NIFTY",
        capital=100000,
        risk_pct=1,
        rr_ratio=2,
        config=BreakoutConfig(lookback=20, min_score=6, cooldown_minutes=20, avoid_open_minutes=5),
    )

    assert len(signals) > 0
    assert signals[0].side in {"BUY", "SELL"}


def test_validation_rejects_signal_without_fvg_zone_or_confluence(monkeypatch):
    import Backend.application.signal_validation as signal_validation

    latest = datetime(2026, 5, 22, 15, 30, tzinfo=timezone.utc)
    candles = [
        {
            "timestamp": latest.isoformat(),
            "open": 22490,
            "high": 22510,
            "low": 22480,
            "close": 22500,
            "volume": 1000,
        }
    ]
    weak_signal = StrategySignal(
        strategy_name="breakout",
        symbol="NIFTY",
        side="BUY",
        entry_price=22500,
        stop_loss=22450,
        target_price=22600,
        signal_time=latest,
        metadata={
            "score": 9,
            "ema_9": 22520,
            "ema_21": 22500,
            "ema_50": 22480,
            "ema_200": 22400,
            "rsi": 62,
            "macd": 12,
            "macd_signal": 8,
        },
    )

    monkeypatch.setattr(
        signal_validation,
        "get_price",
        lambda symbol: {"source": "yahoo-finance", "price": 22500},
    )

    validated, _source = validate_signals(
        [weak_signal],
        symbol="NIFTY",
        candles=candles,
        candle_source="yahoo-finance",
    )
    diagnostics = diagnose_signal_run(
        [weak_signal],
        symbol="NIFTY",
        candles=candles,
        candle_source="yahoo-finance",
    )

    assert len(validated) == 0
    assert any("zone/FVG/supply-demand confluence not present" in item for item in diagnostics)
