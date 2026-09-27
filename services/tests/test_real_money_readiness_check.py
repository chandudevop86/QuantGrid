from __future__ import annotations

from datetime import datetime, timedelta, timezone

from scripts.real_money_readiness_check import evaluate_real_money_evidence


def _trade(day: datetime, *, net_pnl=100.0, total_costs=10.0, status="closed"):
    return {
        "status": status,
        "created_at": day.isoformat(),
        "closed_at": (day + timedelta(hours=1)).isoformat(),
        "net_pnl": net_pnl,
        "total_costs": total_costs,
    }


def test_real_money_evidence_rejects_gross_only_records():
    trades = [
        {
            "status": "closed",
            "created_at": "2026-09-01T10:00:00+05:30",
            "pnl": 500.0,
        }
    ]

    result = evaluate_real_money_evidence(trades, min_sessions=30)

    assert result["passed"] is False
    assert result["missing_cost_evidence"] == 1
    assert "MISSING_COST_ADJUSTED_EVIDENCE:1" in result["blockers"]
    assert "NO_COST_ADJUSTED_CLOSED_TRADES" in result["blockers"]


def test_real_money_evidence_requires_minimum_distinct_sessions():
    start = datetime(2026, 8, 1, 10, tzinfo=timezone.utc)
    trades = [_trade(start + timedelta(days=index)) for index in range(29)]

    result = evaluate_real_money_evidence(trades, min_sessions=30)

    assert result["passed"] is False
    assert result["session_count"] == 29
    assert "INSUFFICIENT_PAPER_SESSIONS:29/30" in result["blockers"]


def test_real_money_evidence_rejects_non_positive_net_expectancy():
    start = datetime(2026, 7, 1, 10, tzinfo=timezone.utc)
    trades = [
        _trade(start + timedelta(days=index), net_pnl=-25.0, total_costs=10.0)
        for index in range(30)
    ]

    result = evaluate_real_money_evidence(trades, min_sessions=30)

    assert result["passed"] is False
    assert result["session_count"] == 30
    assert result["net_expectancy"] == -25.0
    assert "NON_POSITIVE_NET_EXPECTANCY:-25.0" in result["blockers"]


def test_real_money_evidence_passes_30_cost_adjusted_positive_sessions():
    start = datetime(2026, 7, 1, 10, tzinfo=timezone.utc)
    trades = [
        _trade(start + timedelta(days=index), net_pnl=75.0, total_costs=12.5)
        for index in range(30)
    ]

    result = evaluate_real_money_evidence(trades, min_sessions=30)

    assert result["passed"] is True
    assert result["session_count"] == 30
    assert result["cost_adjusted_trades"] == 30
    assert result["net_expectancy"] == 75.0
    assert result["total_costs"] == 375.0
    assert result["blockers"] == []
