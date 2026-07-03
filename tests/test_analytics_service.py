from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVICE_ROOT = ROOT / "services" / "trading-service"
sys.path.insert(0, str(SERVICE_ROOT))

from Backend.application import analytics_service
from Backend.application.analytics_service import AnalyticsService
from Backend.domain.shared import IAnalyticsService


def test_analytics_service_implements_interface_and_ranks_strategies(monkeypatch):
    trades = [
        {"status": "closed", "strategy": "breakout", "pnl": 500},
        {"status": "completed", "strategy": "mean_reversion", "pnl": -100},
        {"status": "closed", "strategy": "breakout", "pnl": 250},
        {"status": "open", "strategy": "ignored", "pnl": 999},
    ]
    monkeypatch.setattr(analytics_service, "list_paper_trades", lambda limit: trades)
    monkeypatch.setattr(
        analytics_service,
        "trade_journal_summary",
        lambda limit=500: {"best_strategy": "breakout", "worst_strategy": "mean_reversion"},
    )

    service = AnalyticsService()
    ranking = service.strategy_ranking()

    assert isinstance(service, IAnalyticsService)
    assert ranking["ranked"][0] == {"strategy": "breakout", "pnl": 750.0}
    assert ranking["best_strategy"] == "breakout"
    assert ranking["worst_strategy"] == "mean_reversion"
