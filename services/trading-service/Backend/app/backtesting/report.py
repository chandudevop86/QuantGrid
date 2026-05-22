from __future__ import annotations

from Backend.app.backtesting.models import BacktestResult


def render_report(result: BacktestResult) -> dict:
    payload = result.to_dict()
    metrics = payload["metrics"]
    payload["summary"] = (
        f"{metrics['total_trades']} trades, {metrics['win_rate']}% win rate, "
        f"PnL {metrics['pnl']}, PF {metrics['profit_factor']}."
    )
    return payload
