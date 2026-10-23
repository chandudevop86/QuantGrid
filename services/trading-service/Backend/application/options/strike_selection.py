"""Deterministic, read-only option strike classification and filtering.

No trade execution is performed by this module.
"""
from dataclasses import dataclass
from enum import Enum
from math import isfinite
from typing import Optional


class Moneyness(str, Enum):
    ATM = "ATM"
    NEAR_ATM = "NEAR_ATM"
    ITM = "ITM"
    DEEP_ITM = "DEEP_ITM"
    OTM = "OTM"
    DEEP_OTM = "DEEP_OTM"


def classify_strike(spot: float, strike: float, side: str, *,
                    atm_tolerance_pct: float = 0.15,
                    near_tolerance_pct: float = 0.5,
                    deep_threshold_pct: float = 2.0) -> Moneyness:
    """Classify by relative spot distance; thresholds are configurable conventions."""
    if not all(isfinite(float(x)) for x in (spot, strike)) or spot <= 0 or strike <= 0:
        raise ValueError("spot and strike must be finite positive numbers")
    if side not in ("CE", "PE"):
        raise ValueError("side must be CE or PE")
    if not (0 <= atm_tolerance_pct <= near_tolerance_pct < deep_threshold_pct):
        raise ValueError("invalid moneyness thresholds")
    distance = abs(strike - spot) / spot * 100
    if distance <= atm_tolerance_pct:
        return Moneyness.ATM
    if distance <= near_tolerance_pct:
        return Moneyness.NEAR_ATM
    itm = strike < spot if side == "CE" else strike > spot
    if itm:
        return Moneyness.DEEP_ITM if distance >= deep_threshold_pct else Moneyness.ITM
    return Moneyness.DEEP_OTM if distance >= deep_threshold_pct else Moneyness.OTM


@dataclass(frozen=True)
class StrikeFilter:
    allowed_moneyness: tuple[Moneyness, ...] = (
        Moneyness.ATM, Moneyness.NEAR_ATM, Moneyness.ITM)
    min_open_interest: int = 1000
    max_spread_pct: float = 5.0
    min_abs_delta: float = 0.25
    max_abs_delta: float = 0.85
    max_quote_age_seconds: int = 30


def evaluate_contract(*, spot: float, strike: float, side: str,
                      bid: Optional[float], ask: Optional[float],
                      open_interest: Optional[int], delta: Optional[float],
                      quote_age_seconds: Optional[float],
                      config: StrikeFilter = StrikeFilter()) -> dict:
    """Fail closed on missing/invalid quotes and Greeks; return explainable reasons."""
    moneyness = classify_strike(spot, strike, side)
    reasons = []
    if moneyness not in config.allowed_moneyness:
        reasons.append("moneyness_not_allowed")
    if bid is None or ask is None or not all(isfinite(float(v)) for v in (bid, ask)) or bid <= 0 or ask < bid:
        reasons.append("invalid_or_missing_quote")
    elif (ask - bid) / ((ask + bid) / 2) * 100 > config.max_spread_pct:
        reasons.append("spread_too_wide")
    if open_interest is None or open_interest < config.min_open_interest:
        reasons.append("insufficient_or_missing_open_interest")
    if delta is None or not isfinite(float(delta)) or not config.min_abs_delta <= abs(delta) <= config.max_abs_delta or (delta < 0) != (side == "PE"):
        reasons.append("invalid_or_out_of_range_delta")
    if quote_age_seconds is None or not isfinite(float(quote_age_seconds)) or not 0 <= quote_age_seconds <= config.max_quote_age_seconds:
        reasons.append("stale_or_missing_quote_timestamp")
    return {"eligible": not reasons, "moneyness": moneyness.value, "reasons": reasons}
