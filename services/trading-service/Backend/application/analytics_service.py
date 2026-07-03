from __future__ import annotations

from typing import Any

from Backend.application.paper_trade_store import list_paper_trades
from Backend.application.quant_modules import trade_journal_summary
from Backend.domain.shared import IAnalyticsService


class AnalyticsService(IAnalyticsService):
    def trade_journal_summary(self, limit: int = 100) -> dict[str, Any]:
        return trade_journal_summary(limit=limit)

    def strategy_ranking(self, limit: int = 500) -> dict[str, Any]:
        summary = trade_journal_summary(limit=limit)
        trades = [
            trade
            for trade in list_paper_trades(limit)
            if str(trade.get("status") or "").lower() in {"closed", "exited", "completed"}
        ]
        strategy_pnl: dict[str, float] = {}
        for trade in trades:
            strategy = str(trade.get("strategy") or trade.get("strategy_name") or "unknown")
            strategy_pnl[strategy] = strategy_pnl.get(strategy, 0.0) + float(trade.get("pnl") or 0.0)
        ranked = [
            {"strategy": strategy, "pnl": round(pnl, 2)}
            for strategy, pnl in sorted(strategy_pnl.items(), key=lambda item: item[1], reverse=True)
        ]
        return {
            "module": "strategy_ranking",
            "ranked": ranked,
            "best_strategy": summary.get("best_strategy"),
            "worst_strategy": summary.get("worst_strategy"),
            "source": "paper_trade_journal",
        }
