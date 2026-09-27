from __future__ import annotations

from datetime import datetime
from typing import Any


CLOSED_STATUSES = {"closed", "exited", "completed"}


def _day(value: Any) -> str | None:
    if value in {None, ""}:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    text = str(value)
    return text[:10] if len(text) >= 10 else None


def evaluate_real_money_evidence(
    trades: list[dict[str, Any]],
    *,
    min_sessions: int = 30,
) -> dict[str, Any]:
    closed = [
        trade
        for trade in trades
        if str(trade.get("status") or "").strip().lower() in CLOSED_STATUSES
    ]

    usable: list[dict[str, Any]] = []
    missing_cost_evidence = 0
    missing_session_date = 0

    for trade in closed:
        day = _day(trade.get("closed_at") or trade.get("created_at") or trade.get("timestamp"))
        if not day:
            missing_session_date += 1
            continue

        if trade.get("net_pnl") is None or trade.get("total_costs") is None:
            missing_cost_evidence += 1
            continue

        try:
            net_pnl = float(trade["net_pnl"])
            total_costs = float(trade["total_costs"])
        except (TypeError, ValueError):
            missing_cost_evidence += 1
            continue

        usable.append({**trade, "_session_day": day, "_net_pnl": net_pnl, "_total_costs": total_costs})

    sessions: dict[str, float] = {}
    for trade in usable:
        day = trade["_session_day"]
        sessions[day] = sessions.get(day, 0.0) + float(trade["_net_pnl"])

    session_count = len(sessions)
    net_pnl_total = round(sum(float(trade["_net_pnl"]) for trade in usable), 2)
    total_costs = round(sum(float(trade["_total_costs"]) for trade in usable), 2)
    expectancy = round(net_pnl_total / len(usable), 2) if usable else 0.0
    positive_session_count = sum(1 for value in sessions.values() if value > 0)

    blockers: list[str] = []
    if session_count < min_sessions:
        blockers.append(f"INSUFFICIENT_PAPER_SESSIONS:{session_count}/{min_sessions}")
    if missing_cost_evidence:
        blockers.append(f"MISSING_COST_ADJUSTED_EVIDENCE:{missing_cost_evidence}")
    if missing_session_date:
        blockers.append(f"MISSING_SESSION_DATE:{missing_session_date}")
    if not usable:
        blockers.append("NO_COST_ADJUSTED_CLOSED_TRADES")
    elif expectancy <= 0:
        blockers.append(f"NON_POSITIVE_NET_EXPECTANCY:{expectancy}")

    return {
        "passed": not blockers,
        "min_sessions": min_sessions,
        "closed_trades": len(closed),
        "cost_adjusted_trades": len(usable),
        "session_count": session_count,
        "positive_session_count": positive_session_count,
        "net_pnl": net_pnl_total,
        "total_costs": total_costs,
        "net_expectancy": expectancy,
        "missing_cost_evidence": missing_cost_evidence,
        "missing_session_date": missing_session_date,
        "blockers": blockers,
        "session_net_pnl": {key: round(value, 2) for key, value in sorted(sessions.items())},
    }
