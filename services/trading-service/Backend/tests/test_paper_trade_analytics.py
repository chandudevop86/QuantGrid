from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVICE_ROOT = ROOT / "services" / "trading-service"
sys.path.insert(0, str(SERVICE_ROOT))

from Backend.application import quant_modules


def test_trade_journal_summary_returns_decision_quality_metrics(monkeypatch):
    trades = [
        {"status": "closed", "pnl": 1000, "strategy": "breakout", "entry": 100, "stop_loss": 95, "target": 110, "created_at": "2026-07-03T09:30:00+00:00"},
        {"status": "closed", "pnl": -400, "strategy": "breakout", "entry": 100, "stop_loss": 96, "target": 108, "created_at": "2026-07-03T10:30:00+00:00"},
        {"status": "completed", "pnl": 600, "strategy_name": "mean_reversion", "entry": 100, "stop_loss": 95, "target": 105, "created_at": "2026-07-04T09:30:00+00:00"},
        {"status": "open", "pnl": 200, "strategy": "ignored", "created_at": "2026-07-04T10:30:00+00:00"},
        {"status": "exited", "pnl": -200, "strategy": "mean_reversion", "entry": 100, "stop_loss": 98, "target": 104, "created_at": "2026-08-01T09:30:00+00:00"},
    ]
    monkeypatch.setattr(quant_modules, "list_paper_trades", lambda limit: trades)

    summary = quant_modules.trade_journal_summary(limit=100)

    assert summary["closed_trades"] == 4
    assert summary["win_rate"] == 0.5
    assert summary["profit_factor"] == 2.67
    assert summary["expectancy"] == 250.0
    assert summary["max_drawdown"] == 400.0
    assert summary["average_win"] == 800.0
    assert summary["average_loss"] == -300.0
    assert summary["average_rr"] == 1.75
    assert summary["best_strategy"] == "breakout"
    assert summary["worst_strategy"] == "mean_reversion"
    assert summary["day_wise_performance"]["2026-07-03"] == 600.0
    assert summary["monthly_performance"]["2026-08"] == -200.0
