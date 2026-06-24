from __future__ import annotations

from Backend.app.backtesting.models import BacktestResult


def render_report(result: BacktestResult) -> dict:
    payload = result.to_dict()
    metrics = payload["metrics"]
    payload.update(
        {
            "total_trades": metrics.get("total_trades", 0),
            "win_rate": metrics.get("win_rate", 0.0),
            "pnl": metrics.get("pnl", 0.0),
            "max_drawdown": metrics.get("max_drawdown", 0.0),
            "sharpe_ratio": metrics.get("sharpe_ratio", 0.0),
            "expectancy": metrics.get("expectancy", 0.0),
        }
    )
    payload["summary"] = (
        f"{metrics['total_trades']} trades, {metrics['win_rate']}% win rate, "
        f"PnL {metrics['pnl']}, Sharpe {metrics.get('sharpe_ratio', 0.0)}, "
        f"Expectancy {metrics.get('expectancy', 0.0)}."
    )
    return payload
