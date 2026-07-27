from __future__ import annotations

from typing import Any

from Backend.domain.models.signal import StrategySignal


def _safe_float(value: Any) -> float | None:
    """
    Safely convert a value to float.

    Returns:
        float if conversion succeeds, otherwise None.
    """
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _trade_shape_reason(signal: StrategySignal) -> str | None:
    """
    Validate trade shape.

    Returns:
        Rejection reason when invalid.
        None when valid.
    """

    entry = float(signal.entry_price)
    stop = float(signal.stop_loss)
    target = float(signal.target_price)

    side = str(signal.side).upper()

    if entry <= 0 or stop <= 0 or target <= 0:
        return "INVALID_PRICE_VALUES"

    risk = abs(entry - stop)
    reward = abs(target - entry)

    if risk <= 0:
        return "INVALID_STOP_LOSS"

    rr = reward / risk

    if rr < 1:
        return f"INVALID_RISK_REWARD:{rr:.2f}"

    if side == "BUY":
        if stop >= entry:
            return "BUY_STOP_MUST_BE_BELOW_ENTRY"

        if target <= entry:
            return "BUY_TARGET_MUST_BE_ABOVE_ENTRY"

    elif side == "SELL":
        if stop <= entry:
            return "SELL_STOP_MUST_BE_ABOVE_ENTRY"

        if target >= entry:
            return "SELL_TARGET_MUST_BE_BELOW_ENTRY"

    else:
        return "INVALID_SIDE"

    return None


def _tqe_response_fields(
    qualification: Any = None,
    *,
    diagnostics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Build Trade Qualification Engine response fields.
    """

    if qualification is not None and hasattr(qualification, "to_dict"):
        qualification = qualification.to_dict()

    qualification = qualification or {}
    diagnostics = diagnostics or {}

    return {
        "trade_quality": {
            "qualified": qualification.get(
                "allowed",
                qualification.get("qualified", False),
            ),
            "risk_reward": qualification.get(
                "rr",
                qualification.get("risk_reward"),
            ),
            "checks": qualification,
        },
        "trade_qualification": qualification,
        "strategy_diagnostics": diagnostics,
    }


def _risk_response_fields(
    *,
    signal: StrategySignal,
    qualification: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Build risk evaluation fields for execution response.
    """

    qualification = qualification or {}

    risk_amount = abs(
        float(signal.entry_price) - float(signal.stop_loss)
    )

    reward_amount = abs(
        float(signal.target_price) - float(signal.entry_price)
    )

    risk_reward = (
        round(reward_amount / risk_amount, 2)
        if risk_amount > 0
        else 0.0
    )

    return {
        "risk": {
            "entry_price": signal.entry_price,
            "stop_loss": signal.stop_loss,
            "target_price": signal.target_price,
            "risk_amount": round(risk_amount, 2),
            "reward_amount": round(reward_amount, 2),
            "risk_reward": risk_reward,
            "passed": qualification.get(
                "risk_reward_passed",
                risk_reward >= 1.5,
            ),
        }
    }