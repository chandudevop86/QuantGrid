from __future__ import annotations

from datetime import datetime, timezone

from Backend.domain.execution_constraints import (
    ExecutionConstraintConfig,
    round_quantity_to_lot,
    validate_execution_constraints,
)
from Backend.domain.models.signal import StrategySignal


def _signal(quantity: int, entry: float = 100.0) -> StrategySignal:
    return StrategySignal(
        strategy_name="test",
        symbol="NIFTY",
        side="BUY",
        entry_price=entry,
        stop_loss=95,
        target_price=110,
        signal_time=datetime.now(timezone.utc),
        metadata={"quantity": quantity},
    )


def test_round_quantity_to_lot_rounds_down():
    assert round_quantity_to_lot(1821, 75) == 1800


def test_execution_constraints_reject_below_one_lot():
    result = validate_execution_constraints(
        _signal(20),
        config=ExecutionConstraintConfig(default_lot_size=75, max_notional=1_000_000),
    )

    assert result.accepted is False
    assert result.reason == "quantity_below_one_lot"
    assert result.quantity == 0


def test_execution_constraints_reject_margin_limit():
    result = validate_execution_constraints(
        _signal(150, entry=10_000),
        config=ExecutionConstraintConfig(default_lot_size=75, max_notional=500_000, margin_multiplier=1.0),
    )

    assert result.accepted is False
    assert result.reason == "margin_limit_exceeded"
    assert result.quantity == 150
    assert result.required_margin == 1_500_000
