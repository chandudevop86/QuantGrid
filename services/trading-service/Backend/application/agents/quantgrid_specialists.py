"""Read-only network, financial-risk and market-research agent primitives.

No broker order placement, external network calls or live trading activation.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone


def _finite_nonnegative(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def network_health_agent(*, api_latency_ms, error_rate, redis_ok, db_ok,
                         worker_lag_seconds, market_feed_age_seconds):
    """Evaluate already-observed telemetry; no active scanning."""
    metrics = (api_latency_ms, error_rate, worker_lag_seconds, market_feed_age_seconds)
    if not all(_finite_nonnegative(x) for x in metrics) or error_rate > 1:
        return {"status": "unknown", "alerts": ["invalid telemetry"], "trading_data_usable": False}
    if type(redis_ok) is not bool or type(db_ok) is not bool:
        return {"status": "unknown", "alerts": ["invalid dependency health"], "trading_data_usable": False}
    alerts = []
    if api_latency_ms > 1000:
        alerts.append("high API latency")
    if error_rate > 0.05:
        alerts.append("elevated API errors")
    if not redis_ok:
        alerts.append("Redis unavailable")
    if not db_ok:
        alerts.append("database unavailable")
    if worker_lag_seconds > 30:
        alerts.append("worker queue lag")
    if market_feed_age_seconds > 15:
        alerts.append("stale market feed")
    return {"status": "degraded" if alerts else "healthy", "alerts": alerts,
            "trading_data_usable": bool(redis_ok and db_ok and market_feed_age_seconds <= 15)}


def financial_risk_agent(*, capital_rupees, reserved_rupees, proposed_premium_rupees,
                         live_enabled=False, kill_switch=True):
    """Conservative research/preflight summary, not an order authorization."""
    values = (capital_rupees, reserved_rupees, proposed_premium_rupees)
    if not all(_finite_nonnegative(x) for x in values):
        return {"approved": False, "reason": "invalid financial inputs"}
    if type(live_enabled) is not bool or type(kill_switch) is not bool:
        return {"approved": False, "reason": "invalid control state"}
    if kill_switch or not live_enabled:
        return {"approved": False, "reason": "live trading disabled"}
    if proposed_premium_rupees <= 0:
        return {"approved": False, "reason": "premium must be positive"}
    if reserved_rupees + proposed_premium_rupees > min(capital_rupees, 5000):
        return {"approved": False, "reason": "premium exposure exceeds cap"}
    return {"approved": False, "reason": "requires authoritative broker and server-side execution preflight"}


def market_research_agent(*, symbol, spot, futures_price, call_oi, put_oi,
                          iv_percent, quote_timestamp, now=None):
    """Explain observed basis/PCR; never generate unconditional buy/sell signals."""
    if symbol not in ("NIFTY", "BANKNIFTY") or not all(
        _finite_nonnegative(v) for v in (spot, futures_price, call_oi, put_oi, iv_percent)
    ) or spot == 0 or call_oi == 0:
        return {"valid": False, "reason": "invalid market observations"}
    try:
        ts = datetime.fromisoformat(quote_timestamp.replace("Z", "+00:00"))
        current = now or datetime.now(timezone.utc)
        if ts.tzinfo is None or not 0 <= (current - ts).total_seconds() <= 15:
            return {"valid": False, "reason": "stale or future quote"}
    except (AttributeError, ValueError, TypeError, OverflowError):
        return {"valid": False, "reason": "invalid quote provenance"}
    return {
        "valid": True, "symbol": symbol, "pcr": round(put_oi / call_oi, 4),
        "futures_basis": round(futures_price - spot, 2),
        "iv_percent": iv_percent,
        "signal": "research_only",
        "note": "PCR and basis alone do not establish directional edge; verify liquidity, costs and expiry.",
    }
