from __future__ import annotations

import math
from typing import Any, cast


def calculate_trade_risk(
    entry_price: float,
    stop_loss: float | None,
    current_price: float,
    reward: float,
) -> float | None:
    """Calculates trade risk metrics while ensuring strict Type-Safe evaluation paths."""
    # Line 42 | Error 1 Fix: Explicitly assert/guard against None before using the minus operator
    if stop_loss is None:
        return None

    risk: float | None = stop_loss - entry_price

    # Line 43 | Error 3 Fix: Verify that risk is not None before attempting int/float comparisons
    if risk is None:
        return None

    if risk < 0:
        risk = abs(risk)

    # Line 43 | Error 2 Fix: Protect the division space from executing on a None denominator
    if risk == 0:
        return None

    rr = reward / risk
    return rr


def compute_final_position(
    account_balance: float, 
    risk_pct: float, 
    sl_distance: float | None
) -> float:
    """Computes rounded position sizing metrics while protecting built-in math wrappers."""
    if sl_distance is None or sl_distance <= 0:
        return 0.0

    position_size: float | None = (account_balance * risk_pct) / sl_distance

    # Line 52 | Error 4 Fix: Extract fallback return context prior to evaluating round()
    if position_size is None:
        return 0.0

    return round(position_size, 2)


def verify_order_bounds(sl: float | None, entry: float) -> bool:
    """Verifies that the protective stop boundaries align safely with entry parameters."""
    # Line 63 | Error 5 Fix: Drop validation window early if the optional parameter is empty
    if sl is None:
        return False

    if sl <= entry:
        return True
    return False


def extract_market_quote(record: dict[str, Any]) -> float:
    """Extracts a valid floating-point execution target price from raw incoming dictionaries."""
    # Line 173 | Error 6 Fix: Isolate dictionary payload values to clean intermediate parameters
    value = record.get("price")

    if value is None:
        raise ValueError("Missing critical price metadata fields in streaming record payload")

    return float(value)
