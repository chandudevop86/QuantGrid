from __future__ import annotations

from dataclasses import dataclass

from app.modules.portfolio.domain.enums import TransactionType
from app.modules.portfolio.domain.exceptions import (
    InsufficientHoldingQuantityError,
    InvalidTransactionError,
)


@dataclass(slots=True)
class PositionState:
    """Running position state (quantity + weighted average cost) for one symbol."""

    quantity: float = 0.0
    average_cost: float = 0.0
    realized_pnl: float = 0.0

    @property
    def invested_value(self) -> float:
        return self.quantity * self.average_cost


class PositionEngine:
    """
    Pure domain service that folds a `TransactionRecord` into a `PositionState`.

    This encapsulates the weighted-average-cost accounting rules for every
    supported corporate action / transaction type, independent of persistence.
    """

    @staticmethod
    def apply(state: PositionState, *, symbol: str, transaction_type: TransactionType,
              quantity: float, price: float, fees: float = 0.0,
              split_ratio_from: float | None = None,
              split_ratio_to: float | None = None) -> PositionState:

        if quantity is not None and quantity < 0:
            raise InvalidTransactionError("Transaction quantity cannot be negative.")

        if transaction_type == TransactionType.BUY:
            total_cost_existing = state.quantity * state.average_cost
            total_cost_new = quantity * price + fees
            new_quantity = state.quantity + quantity
            state.average_cost = (
                (total_cost_existing + total_cost_new) / new_quantity
                if new_quantity > 0 else 0.0
            )
            state.quantity = new_quantity

        elif transaction_type == TransactionType.SELL:
            if quantity > state.quantity + 1e-9:
                raise InsufficientHoldingQuantityError(symbol, state.quantity, quantity)
            realized = (price - state.average_cost) * quantity - fees
            state.realized_pnl += realized
            state.quantity -= quantity
            if state.quantity <= 1e-9:
                state.quantity = 0.0
                state.average_cost = 0.0

        elif transaction_type == TransactionType.DIVIDEND:
            # Cash dividend does not change quantity/average cost of the position itself;
            # it is tracked separately as a cash inflow (handled by cash-flow builder).
            pass

        elif transaction_type == TransactionType.BONUS:
            # `quantity` here represents the number of bonus shares issued.
            total_cost_existing = state.quantity * state.average_cost
            new_quantity = state.quantity + quantity
            state.average_cost = (
                total_cost_existing / new_quantity if new_quantity > 0 else 0.0
            )
            state.quantity = new_quantity

        elif transaction_type == TransactionType.SPLIT:
            if not split_ratio_from or not split_ratio_to or split_ratio_from <= 0:
                raise InvalidTransactionError(
                    "A SPLIT transaction requires positive split_ratio_from/split_ratio_to."
                )
            factor = split_ratio_to / split_ratio_from
            state.quantity = state.quantity * factor
            state.average_cost = (
                state.average_cost / factor if factor > 0 else state.average_cost
            )

        else:  # pragma: no cover - defensive
            raise InvalidTransactionError(f"Unsupported transaction type: {transaction_type}")

        return state
