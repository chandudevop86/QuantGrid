from __future__ import annotations

from Backend.app.backtesting.metrics import calculate_metrics
from Backend.app.backtesting.models import BacktestTrade


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
