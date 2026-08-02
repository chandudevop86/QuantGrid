from __future__ import annotations

from datetime import datetime

from Backend.app.backtesting.metrics import calculate_metrics
from Backend.app.backtesting.models import BacktestTrade
from Backend.application.quant_modules import backtesting_module
from Backend.domain.models.signal import StrategySignal
from Backend.trading_system.backtesting import BacktestEngine as CanonicalBacktestEngine


def _provider_candles():
    return [
        {"timestamp": f"2026-07-04T09:{index:02d}:00+00:00", "open": 100 + index, "high": 102 + index, "low": 98 + index, "close": 101 + index, "volume": 1000}
        for index in range(20)
    ]


def _trade(pnl: float, outcome: str) -> BacktestTrade:
    return BacktestTrade(
        strategy="test",
        symbol="NIFTY",
        side="BUY",
        entry=100,
        stop_loss=95,
        target=110,
        quantity=1,
        entry_time="2026-05-22T03:00:00+00:00",
        exit_time="2026-05-22T03:05:00+00:00",
        exit_price=110 if pnl > 0 else 95,
        pnl=pnl,
        rr=2.0,
        outcome=outcome,
        metadata={"gross_pnl": pnl + 5, "total_costs": 5, "latency_ms": 25},
    )


def test_backtest_metrics_calculation():
    metrics = calculate_metrics([_trade(100, "win"), _trade(-50, "loss"), _trade(150, "win")])

    assert metrics["total_trades"] == 3
    assert metrics["win_rate"] == 66.67
    assert metrics["pnl"] == 200
    assert metrics["profit_factor"] == 5
    assert metrics["gross_pnl"] == 215
    assert metrics["total_costs"] == 15
    assert metrics["net_pnl"] == 200
    assert metrics["average_latency_ms"] == 25
    assert metrics["winning_streak"] == 1
    assert metrics["losing_streak"] == 1


def test_backtesting_module_returns_cost_model_assumptions():
    result = backtesting_module({"symbol": "NIFTY", "brokerage_per_order": 15, "slippage_bps": 3, "candles": _provider_candles()})

    cost_model = result["cost_model"]
    assert cost_model["brokerage_per_order"] == 15
    assert cost_model["slippage_bps"] == 3
    assert "spread_bps" in cost_model
    assert "entry_delay_seconds" in cost_model
    assert "liquidity_filter" in cost_model
    assert "expiry_behavior" in cost_model
    assert cost_model["applied_to_results"] is True
    assert cost_model["effective_slippage_per_side_bps"] == 7


def test_backtesting_module_applies_configured_cost_model_to_engine(monkeypatch):
    from Backend.application import quant_modules

    captured = {}

    class FakeResult:
        def to_dict(self):
            return {
                "total_trades": 0,
                "win_rate": 0,
                "gross_pnl": 0,
                "total_costs": 0,
                "net_pnl": 0,
                "pnl": 0,
                "expectancy": 0,
                "max_drawdown": 0,
                "sharpe_ratio": 0,
                "rejected_signal_count": 0,
                "average_latency_ms": 0,
                "trades": [],
            }

    class FakeEngine:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def run(self, **_kwargs):
            return FakeResult()

    monkeypatch.setattr(quant_modules, "BacktestEngine", FakeEngine)

    result = quant_modules.backtesting_module(
        {
            "symbol": "NIFTY",
            "brokerage_per_order": 12,
            "brokerage_bps": 1.5,
            "taxes_bps": 3,
            "slippage_bps": 4,
            "spread_bps": 6,
            "entry_delay_seconds": 2,
            "candles": _provider_candles(),
        }
    )

    assert captured["brokerage_per_order"] == 12
    assert captured["brokerage_bps"] == 1.5
    assert captured["taxes_bps"] == 3
    assert captured["latency_ms"] == 2000
    assert captured["slippage_model"].config.fixed_bps == 7
    assert result["cost_model"]["effective_slippage_per_side_bps"] == 7


def test_backtesting_module_honors_max_candles_cap():
    candles = [
        {"timestamp": f"2026-07-04T09:{index:02d}:00+00:00", "open": 100 + index, "high": 102 + index, "low": 98 + index, "close": 101 + index, "volume": 1000}
        for index in range(20)
    ]

    result = backtesting_module({"symbol": "NIFTY", "candles": candles, "max_candles": 5})

    assert result["payload"]["candles"] == 5


def test_legacy_backtest_api_adapter_uses_canonical_engine_without_synthetic_fallback(monkeypatch):
    from Backend.app.backtesting import engine as legacy_engine

    class CanonicalResult:
        trades = []
        rejected_signal_count = 3
        rejection_reasons = {"below_min_score": 3}

    class FakeCanonicalEngine:
        def __init__(self, **_kwargs):
            pass

        def run(self, **_kwargs):
            return CanonicalResult()

    monkeypatch.setattr(legacy_engine, "CanonicalBacktestEngine", FakeCanonicalEngine)

    result = legacy_engine.BacktestEngine().run(
        strategy="amd",
        symbol="NIFTY",
        candles=[
            {"timestamp": "2026-07-04T09:15:00+05:30", "open": 100, "high": 101, "low": 99, "close": 100, "volume": 1000}
        ],
    )

    assert result.trades == []
    assert result.metrics["rejected_signal_count"] == 3
    assert result.metrics["rejection_reasons"] == {"below_min_score": 3}
    assert result.metrics["simulation_engine"] == "canonical_trading_system"
    assert result.metrics["synthetic_trade_fallback"] is False


def test_canonical_backtest_reports_duplicate_and_low_score_rejections():
    candles = [
        {"timestamp": f"2026-07-04T09:{15 + index:02d}:00", "open": 100, "high": 101, "low": 99, "close": 100, "volume": 1000}
        for index in range(3)
    ]
    signal = StrategySignal(
        strategy_name="test",
        symbol="NIFTY",
        side="BUY",
        entry_price=100,
        stop_loss=95,
        target_price=110,
        signal_time=datetime.fromisoformat("2026-07-04T09:15:00"),
        metadata={"score": 5},
    )

    result = CanonicalBacktestEngine().run(
        candles=candles,
        signals=[signal, signal],
        strategy_name="test",
        symbol="NIFTY",
        min_score=10,
    )

    assert result.rejected_signal_count == 2
    assert result.rejection_reasons == {"below_min_score": 1, "duplicate_signal": 1}
