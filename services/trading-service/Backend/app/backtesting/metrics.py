from __future__ import annotations

import math
from typing import Any

from Backend.app.backtesting.models import BacktestTrade


def _streak(values: list[bool]) -> int:
    best = current = 0
    for value in values:
        if value:
            current += 1
            best = max(best, current)
        else:
            current = 0
    return best


def calculate_metrics(trades: list[BacktestTrade]) -> dict[str, Any]:
    if not trades:
        return {
            "total_trades": 0,
            "win_rate": 0.0,
            "pnl": 0.0,
            "max_drawdown": 0.0,
            "profit_factor": 0.0,
            "sharpe_ratio": 0.0,
            "expectancy": 0.0,
            "average_rr": 0.0,
            "best_setup_type": None,
            "losing_streak": 0,
            "winning_streak": 0,
        }

    pnls = [float(trade.pnl) for trade in trades]
    wins = [pnl > 0 for pnl in pnls]
    gross_profit = sum(pnl for pnl in pnls if pnl > 0)
    gross_loss = abs(sum(pnl for pnl in pnls if pnl < 0))
    equity = 0.0
    peak = 0.0
    max_drawdown = 0.0
    for pnl in pnls:
        equity += pnl
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, peak - equity)

    mean = sum(pnls) / len(pnls)
    variance = sum((pnl - mean) ** 2 for pnl in pnls) / len(pnls)
    std = math.sqrt(variance)
    sharpe = (mean / std * math.sqrt(len(pnls))) if std > 0 else 0.0
    setup_pnl: dict[str, float] = {}
    for trade in trades:
        setup_type = str(trade.metadata.get("setup_type") or "unknown")
        setup_pnl[setup_type] = setup_pnl.get(setup_type, 0.0) + float(trade.pnl)

    return {
        "total_trades": len(trades),
        "win_rate": round(sum(wins) / len(trades) * 100, 2),
        "pnl": round(sum(pnls), 2),
        "max_drawdown": round(max_drawdown, 2),
        "profit_factor": round(gross_profit / gross_loss, 2) if gross_loss > 0 else round(gross_profit, 2),
        "sharpe_ratio": round(sharpe, 2),
        "expectancy": round(mean, 2),
        "average_rr": round(sum(float(trade.rr) for trade in trades) / len(trades), 2),
        "best_setup_type": max(setup_pnl, key=setup_pnl.get) if setup_pnl else None,
        "losing_streak": _streak([not item for item in wins]),
        "winning_streak": _streak(wins),
    }
