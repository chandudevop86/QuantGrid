"""Fail-closed validation for proposed NIFTY option paper orders.

Validation only. Does not place orders or create positions.
"""
from datetime import datetime, timezone
from math import isfinite
from Backend.application.options.strike_selection import evaluate_contract


def validate_option_paper_order(*, symbol, side, spot, strike, expiry,
                                security_id, bid, ask, open_interest, delta,
                                quote_timestamp, lot_size, lots,
                                execution_mode="paper", max_premium_rupees=100000):
    reasons = []
    if execution_mode != "paper":
        reasons.append("live_execution_forbidden")
    if symbol != "NIFTY" or side not in ("CE", "PE"):
        reasons.append("invalid_instrument")
    if not security_id or not str(security_id).isdigit():
        reasons.append("missing_contract_identity")
    if not isinstance(lot_size, int) or isinstance(lot_size, bool) or lot_size <= 0:
        reasons.append("invalid_exchange_lot_size")
    if not isinstance(lots, int) or isinstance(lots, bool) or not 1 <= lots <= 10:
        reasons.append("invalid_lot_count")
    try:
        expiry_date = datetime.fromisoformat(str(expiry)).date()
        if expiry_date < datetime.now(timezone.utc).date():
            reasons.append("expired_contract")
    except (TypeError, ValueError):
        reasons.append("invalid_expiry")
    try:
        timestamp = datetime.fromisoformat(str(quote_timestamp).replace("Z", "+00:00"))
        if timestamp.tzinfo is None:
            raise ValueError("timezone required")
        age = (datetime.now(timezone.utc) - timestamp.astimezone(timezone.utc)).total_seconds()
        if not 0 <= age <= 30:
            reasons.append("stale_quote")
    except (TypeError, ValueError):
        age = None
        reasons.append("invalid_quote_timestamp")
    try:
        check = evaluate_contract(
            spot=float(spot), strike=float(strike), side=side,
            bid=bid, ask=ask, open_interest=open_interest,
            delta=delta, quote_age_seconds=age,
        )
        reasons.extend(check["reasons"])
    except (TypeError, ValueError, OverflowError):
        reasons.append("invalid_contract_data")
    try:
        premium = float(ask)
        valid_premium = isfinite(premium) and premium > 0
    except (TypeError, ValueError, OverflowError):
        premium = 0.0
        valid_premium = False
    if not valid_premium:
        reasons.append("invalid_premium")
        estimated_cost = None
    elif isinstance(lot_size, int) and isinstance(lots, int) and lot_size > 0 and lots > 0:
        estimated_cost = premium * lot_size * lots
        if estimated_cost > max_premium_rupees:
            reasons.append("premium_risk_limit_exceeded")
    else:
        estimated_cost = None
    return {"eligible": not reasons, "reasons": sorted(set(reasons)),
            "estimated_premium_rupees": estimated_cost,
            "execution_mode": "paper", "execution_enabled": False}
