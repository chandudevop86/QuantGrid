from __future__ import annotations

import os
from dataclasses import dataclass
from math import floor

from Backend.domain.models.order import Order
from Backend.domain.models.signal import StrategySignal


DEFAULT_LOT_SIZES = {
    "NIFTY": 65,
    "NIFTY50": 65,
    "NIFTY_50": 65,
    "BANKNIFTY": 35,
    "NIFTYBANK": 35,
    "FINNIFTY": 65,
    "MIDCPNIFTY": 120,
}


@dataclass(frozen=True, slots=True)
class ExecutionConstraintConfig:
    default_lot_size: int = 1
    max_notional: float = 1_000_000.0
    margin_multiplier: float = 1.0
    round_down_to_lot: bool = True


@dataclass(frozen=True, slots=True)
class ExecutionConstraintResult:
    accepted: bool
    reason: str
    quantity: int
    lot_size: int
    notional: float
    required_margin: float


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes"}


def _symbol_key(symbol: str) -> str:
    return symbol.upper().replace(" ", "").replace("-", "_")


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def constraint_config() -> ExecutionConstraintConfig:
    return ExecutionConstraintConfig(
        default_lot_size=max(1, _int_env("QUANTGRID_DEFAULT_LOT_SIZE", 1)),
        max_notional=max(0.0, _float_env("QUANTGRID_MAX_ORDER_NOTIONAL", 1_000_000.0)),
        margin_multiplier=max(0.0, _float_env("QUANTGRID_MARGIN_MULTIPLIER", 1.0)),
        round_down_to_lot=_truthy(os.getenv("QUANTGRID_ROUND_DOWN_TO_LOT", "true")),
    )


def lot_size_for_symbol(symbol: str, config: ExecutionConstraintConfig | None = None) -> int:
    config = config or constraint_config()
    key = _symbol_key(symbol)
    env_specific = os.getenv(f"QUANTGRID_LOT_SIZE_{key}")
    if env_specific:
        try:
            return max(1, int(env_specific))
        except ValueError:
            pass
    return DEFAULT_LOT_SIZES.get(key, config.default_lot_size)


def requested_quantity(signal: StrategySignal) -> int:
    try:
        return int(signal.metadata.get("quantity", 1))
    except (TypeError, ValueError):
        return 0


def round_quantity_to_lot(quantity: int, lot_size: int, *, round_down: bool = True) -> int:
    if quantity <= 0 or lot_size <= 0:
        return 0
    if quantity % lot_size == 0:
        return quantity
    if round_down:
        return floor(quantity / lot_size) * lot_size
    return quantity + (lot_size - quantity % lot_size)


def validate_execution_constraints(
    signal: StrategySignal,
    *,
    config: ExecutionConstraintConfig | None = None,
) -> ExecutionConstraintResult:
    config = config or constraint_config()
    lot_size = lot_size_for_symbol(signal.symbol, config)
    original_quantity = requested_quantity(signal)
    quantity = round_quantity_to_lot(original_quantity, lot_size, round_down=config.round_down_to_lot)
    notional = round(abs(float(signal.entry_price) * quantity), 2)
    required_margin = round(notional * config.margin_multiplier, 2)

    if original_quantity <= 0:
        return ExecutionConstraintResult(False, "quantity_must_be_positive", quantity, lot_size, notional, required_margin)
    if quantity <= 0:
        return ExecutionConstraintResult(False, "quantity_below_one_lot", quantity, lot_size, notional, required_margin)
    if required_margin > config.max_notional:
        return ExecutionConstraintResult(False, "margin_limit_exceeded", quantity, lot_size, notional, required_margin)

    return ExecutionConstraintResult(True, "ok", quantity, lot_size, notional, required_margin)


def apply_order_constraints(order: Order, result: ExecutionConstraintResult, original_quantity: int) -> Order:
    order.quantity = result.quantity
    order.metadata.update(
        {
            "requested_quantity": original_quantity,
            "rounded_quantity": result.quantity,
            "lot_size": result.lot_size,
            "notional": result.notional,
            "required_margin": result.required_margin,
            "quantity_rounding": "lot_size",
        }
    )
    return order
