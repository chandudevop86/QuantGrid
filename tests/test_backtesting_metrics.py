from __future__ import annotations

from Backend.app.backtesting.metrics import calculate_metrics
from Backend.app.backtesting.models import BacktestTrade
from Backend.application.quant_modules import backtesting_module


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
    result = backtesting_module({"symbol": "NIFTY", "brokerage_per_order": 15, "slippage_bps": 3})

    cost_model = result["cost_model"]
    assert cost_model["brokerage_per_order"] == 15
    assert cost_model["slippage_bps"] == 3
    assert "spread_bps" in cost_model
    assert "entry_delay_seconds" in cost_model
    assert "liquidity_filter" in cost_model
    assert "expiry_behavior" in cost_model


def test_backtesting_module_honors_max_candles_cap():
    candles = [
        {"timestamp": f"2026-07-04T09:{index:02d}:00+00:00", "open": 100 + index, "high": 102 + index, "low": 98 + index, "close": 101 + index, "volume": 1000}
        for index in range(20)
    ]

    result = backtesting_module({"symbol": "NIFTY", "candles": candles, "max_candles": 5})

    assert result["payload"]["candles"] == 5
