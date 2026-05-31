from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SERVICE_ROOT = ROOT / "services" / "trading-service"
sys.path.insert(0, str(SERVICE_ROOT))

from Backend.app.backtesting.metrics import calculate_metrics
from Backend.app.backtesting.models import BacktestTrade
from Backend.application import signal_validation
from Backend.domain.crt_tbs.liquidity import LiquiditySweepDetector
from Backend.domain.engine.strategy_engine import StrategyEngine
from Backend.domain.indicators.indicators import IndicatorService
from Backend.domain.models.context import StrategyContext
from Backend.domain.strategies.crt_tbs import CRTTBSConfig, CRTTBSStrategy


def _crt_tbs_candles() -> list[dict]:
    start = datetime(2026, 5, 29, 9, 15, tzinfo=timezone.utc)
    candles: list[dict] = []
    price = 100.0
    for index in range(24):
        open_price = price
        close = price + 0.18
        candles.append(
            {
                "timestamp": (start + timedelta(minutes=index)).isoformat(),
                "open": open_price,
                "high": close + 0.55,
                "low": open_price - 0.55,
                "close": close,
                "volume": 1000 + index * 4,
            }
        )
        price = close

    candles.append(
        {
            "timestamp": (start + timedelta(minutes=24)).isoformat(),
            "open": 94.0,
            "high": 110.0,
            "low": 90.0,
            "close": 108.2,
            "volume": 2600,
        }
    )
    for offset, close in enumerate([105.6, 103.8, 102.4, 101.2, 100.8], start=25):
        candles.append(
            {
                "timestamp": (start + timedelta(minutes=offset)).isoformat(),
                "open": close + 0.2,
                "high": close + 0.9,
                "low": close - 0.9,
                "close": close,
                "volume": 1500,
            }
        )

    candles.append(
        {
            "timestamp": (start + timedelta(minutes=30)).isoformat(),
            "open": 100.4,
            "high": 104.2,
            "low": 89.0,
            "close": 103.2,
            "volume": 3400,
        }
    )
    candles.append(
        {
            "timestamp": (start + timedelta(minutes=31)).isoformat(),
            "open": 103.2,
            "high": 106.0,
            "low": 102.6,
            "close": 105.4,
            "volume": 2400,
        }
    )
    return candles


def test_liquidity_sweep_detector_finds_sell_side_sweep():
    frame = IndicatorService().prepare(_crt_tbs_candles())
    sweeps = LiquiditySweepDetector(lookback=20).detect(frame, 30)

    assert any(sweep.type == "SSL" and sweep.swept for sweep in sweeps)
    assert next(sweep for sweep in sweeps if sweep.type == "SSL").level == 90.0


def test_crt_tbs_strategy_generates_institutional_buy_signal():
    strategy = CRTTBSStrategy(CRTTBSConfig(require_htf_alignment=False, min_trade_score=5))
    signals = strategy.run(
        _crt_tbs_candles(),
        StrategyContext(symbol="NIFTY", capital=100000, risk_pct=1, rr_ratio=2),
    )

    assert signals
    signal = signals[-1]
    assert signal.strategy_name == "CRT TBS"
    assert signal.side == "BUY"
    assert signal.metadata["crt_range"]["high"] == 110.0
    assert signal.metadata["liquidity_sweep"]["type"] == "SSL"
    assert signal.metadata["trap_type"] == "bear_trap"
    assert signal.metadata["quality_tier"] in {"MEDIUM QUALITY", "HIGH QUALITY"}
    assert signal.metadata["risk_reward"] >= 2.0
    assert signal.metadata["target_2"] > signal.metadata["target_1"] > signal.entry_price


def test_strategy_engine_exposes_crt_tbs():
    engine = StrategyEngine()

    assert "crt_tbs" in engine.available()


def test_crt_tbs_signal_validator_accepts_liquidity_quality_signal(monkeypatch):
    strategy = CRTTBSStrategy(CRTTBSConfig(require_htf_alignment=False, min_trade_score=5))
    candles = _crt_tbs_candles()
    signal = strategy.run(candles, StrategyContext(symbol="NIFTY", capital=100000, risk_pct=1, rr_ratio=2))[-1]

    monkeypatch.setattr(signal_validation, "get_price", lambda _symbol: {"source": "yahoo-finance", "price": signal.entry_price})
    valid, source = signal_validation.validate_signals(
        [signal],
        symbol="NIFTY",
        candles=candles,
        candle_source="yahoo-finance",
    )

    assert source == "live"
    assert valid == [signal]


def test_backtest_metrics_include_best_setup_type():
    trade = BacktestTrade(
        strategy="crt_tbs",
        symbol="NIFTY",
        side="BUY",
        entry=100,
        stop_loss=95,
        target=110,
        quantity=1,
        entry_time="2026-05-29T09:30:00+00:00",
        exit_time="2026-05-29T09:45:00+00:00",
        exit_price=110,
        pnl=10,
        rr=2,
        outcome="win",
        metadata={"setup_type": "CRT reversal + bear_trap"},
    )

    metrics = calculate_metrics([trade])

    assert metrics["average_rr"] == 2
    assert metrics["best_setup_type"] == "CRT reversal + bear_trap"
