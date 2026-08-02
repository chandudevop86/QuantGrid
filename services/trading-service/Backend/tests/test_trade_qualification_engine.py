from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVICE_ROOT = ROOT / "services" / "trading-service"
sys.path.insert(0, str(SERVICE_ROOT))

from Backend.app.backtesting.metrics import calculate_metrics
from Backend.app.backtesting.models import BacktestTrade
from Backend.application.trade_qualification_engine import TradeQualificationEngine
from Backend.domain.models.signal import StrategySignal


def _trend_candles(count: int = 60) -> list[dict]:
    start = datetime(2026, 5, 29, 9, 15, tzinfo=timezone.utc)
    candles: list[dict] = []
    price = 100.0
    for index in range(count):
        open_price = price
        close = open_price + 0.12
        candles.append(
            {
                "timestamp": (start + timedelta(minutes=index)).isoformat(),
                "open": open_price,
                "high": close + 0.12,
                "low": open_price - 0.08,
                "close": close,
                "volume": 1000 + index * 20,
            }
        )
        price = close
    return candles


def _signal(**overrides) -> StrategySignal:
    data = {
        "strategy_name": "Breakout",
        "symbol": "NIFTY",
        "side": "BUY",
        "entry_price": 107.0,
        "stop_loss": 105.0,
        "target_price": 111.5,
        "signal_time": datetime(2026, 5, 29, 10, 14, tzinfo=timezone.utc),
        "metadata": {"score": 9, "quantity": 25},
    }
    data.update(overrides)
    return StrategySignal(**data)


def test_tqe_scores_high_quality_aligned_trade():
    qualification = TradeQualificationEngine().qualify(
        _signal(),
        candles=_trend_candles(),
        h1_candles=_trend_candles(),
        m15_candles=_trend_candles(),
        capital=100000,
        risk_pct=1,
    )

    assert qualification.allowed is True
    assert qualification.market_context == "UPTREND"
    assert qualification.trend_aligned is True
    assert qualification.rr >= 2
    assert qualification.position_sizing.risk_amount == 1000
    assert qualification.position_sizing.position_size == 500
    assert qualification.quality_grade in {"A+", "A", "B"}


def test_tqe_rejects_low_risk_reward():
    qualification = TradeQualificationEngine().qualify(
        _signal(target_price=109.0),
        candles=_trend_candles(),
        capital=100000,
        risk_pct=1,
    )

    assert qualification.allowed is False
    assert qualification.reason == "RR_BELOW_2"
    assert qualification.score_breakdown["risk_reward"] == 0


def test_tqe_annotation_adds_dashboard_metadata():
    signal = _signal()
    annotated = TradeQualificationEngine().annotate_signal(
        signal,
        candles=_trend_candles(),
        capital=100000,
        risk_pct=1,
    )

    assert annotated.metadata["trade_qualification"]["max_score"] == 12
    assert annotated.metadata["quality_grade"] == annotated.metadata["trade_qualification"]["quality_grade"]
    assert annotated.metadata["market_context"] == "UPTREND"
    assert annotated.metadata["position_size"] > 0


def test_backtesting_metrics_report_win_rate_by_tqe_grade():
    trades = [
        BacktestTrade(
            strategy="Breakout",
            symbol="NIFTY",
            side="BUY",
            entry=100,
            stop_loss=95,
            target=110,
            quantity=1,
            entry_time="2026-05-29T09:30:00+00:00",
            exit_time="2026-05-29T09:40:00+00:00",
            exit_price=110,
            pnl=10,
            rr=2,
            outcome="win",
            metadata={"quality_grade": "A+"},
        ),
        BacktestTrade(
            strategy="Breakout",
            symbol="NIFTY",
            side="BUY",
            entry=100,
            stop_loss=95,
            target=110,
            quantity=1,
            entry_time="2026-05-29T10:30:00+00:00",
            exit_time="2026-05-29T10:40:00+00:00",
            exit_price=95,
            pnl=-5,
            rr=2,
            outcome="loss",
            metadata={"quality_grade": "B"},
        ),
    ]

    metrics = calculate_metrics(trades)

    assert metrics["win_rate_by_grade"]["A+"] == 100
    assert metrics["win_rate_by_grade"]["B"] == 0
