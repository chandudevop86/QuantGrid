from __future__ import annotations

from dataclasses import dataclass

from app.modules.portfolio.domain.entities import HoldingSnapshot
from app.modules.portfolio.domain.exceptions import InsufficientDataError


@dataclass(slots=True)
class RebalancingSuggestion:
    symbol: str
    current_weight_percent: float
    target_weight_percent: float
    drift_percent: float
    action: str  # "BUY" | "SELL" | "HOLD"
    suggested_amount: float  # currency amount to buy/sell to reach target


class RebalancingEngine:
    """
    Pure engine that compares current holding weights against a target
    allocation map (symbol -> target weight %) and proposes buy/sell actions,
    plus a drift-band tolerance to avoid suggesting churn on tiny deviations.
    """

    @staticmethod
    def suggest(holdings: list[HoldingSnapshot], target_weights: dict[str, float],
                drift_tolerance_percent: float = 2.0) -> list[RebalancingSuggestion]:
        total_value = sum(h.market_value for h in holdings)
        if total_value <= 0:
            raise InsufficientDataError("Portfolio has no positive market value to rebalance.")

        current_by_symbol = {h.symbol: h.market_value for h in holdings}
        all_symbols = set(current_by_symbol) | set(target_weights)

        suggestions: list[RebalancingSuggestion] = []
        for symbol in sorted(all_symbols):
            current_value = current_by_symbol.get(symbol, 0.0)
            current_weight = (current_value / total_value) * 100.0
            target_weight = target_weights.get(symbol, 0.0)
            drift = current_weight - target_weight
            target_value = (target_weight / 100.0) * total_value
            delta_value = target_value - current_value

            if abs(drift) <= drift_tolerance_percent:
                action = "HOLD"
                suggested_amount = 0.0
            elif delta_value > 0:
                action = "BUY"
                suggested_amount = round(delta_value, 2)
            else:
                action = "SELL"
                suggested_amount = round(abs(delta_value), 2)

            suggestions.append(
                RebalancingSuggestion(
                    symbol=symbol,
                    current_weight_percent=round(current_weight, 2),
                    target_weight_percent=round(target_weight, 2),
                    drift_percent=round(drift, 2),
                    action=action,
                    suggested_amount=suggested_amount,
                )
            )
        return sorted(suggestions, key=lambda s: abs(s.drift_percent), reverse=True)
