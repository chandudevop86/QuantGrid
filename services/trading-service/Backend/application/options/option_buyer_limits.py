"""Risk policy for NIFTY option buyer; does not execute orders."""
from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True)
class OptionBuyerLimits:
    paper_max_premium_rupees: float = 100000.0
    live_max_total_exposure_rupees: float = 5000.0
    live_max_lots_per_order: int = 1
    live_enabled: bool = False


def check_live_budget(*, ask: float, lot_size: int, lots: int,
                      existing_open_premium_rupees: float,
                      pending_reserved_premium_rupees: float = 0.0,
                      limits: OptionBuyerLimits = OptionBuyerLimits()) -> dict:
    """Preflight only; real orders also require atomic reservation and broker checks."""
    reasons = []
    values = (ask, existing_open_premium_rupees, pending_reserved_premium_rupees)
    if not all(isfinite(float(v)) and float(v) >= 0 for v in values):
        reasons.append("invalid_exposure_or_quote")
    if type(lot_size) is not int or lot_size <= 0 or type(lots) is not int or not 1 <= lots <= limits.live_max_lots_per_order:
        reasons.append("invalid_lot_size_or_count")
    projected = None
    if not reasons:
        projected = ask * lot_size * lots + existing_open_premium_rupees + pending_reserved_premium_rupees
        if projected > limits.live_max_total_exposure_rupees:
            reasons.append("live_exposure_cap_exceeded")
    if not limits.live_enabled:
        reasons.append("live_execution_disabled")
    return {"eligible": not reasons, "reasons": reasons,
            "projected_exposure_rupees": projected,
            "max_exposure_rupees": limits.live_max_total_exposure_rupees}
