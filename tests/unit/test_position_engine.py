from __future__ import annotations

import pytest

from app.modules.portfolio.domain.calculations.position_engine import PositionEngine, PositionState
from app.modules.portfolio.domain.enums import TransactionType
from app.modules.portfolio.domain.exceptions import InsufficientHoldingQuantityError, InvalidTransactionError


def test_buy_sets_initial_average_cost():
    state = PositionState()
    state = PositionEngine.apply(
        state, symbol="AAPL", transaction_type=TransactionType.BUY, quantity=10, price=100.0, fees=0.0
    )
    assert state.quantity == 10
    assert state.average_cost == pytest.approx(100.0)


def test_buy_updates_weighted_average_cost():
    state = PositionState(quantity=10, average_cost=100.0)
    state = PositionEngine.apply(
        state, symbol="AAPL", transaction_type=TransactionType.BUY, quantity=10, price=200.0, fees=0.0
    )
    assert state.quantity == 20
    assert state.average_cost == pytest.approx(150.0)


def test_buy_includes_fees_in_average_cost():
    state = PositionState()
    state = PositionEngine.apply(
        state, symbol="AAPL", transaction_type=TransactionType.BUY, quantity=10, price=100.0, fees=50.0
    )
    # (10*100 + 50) / 10 = 105
    assert state.average_cost == pytest.approx(105.0)


def test_sell_reduces_quantity_and_realizes_pnl():
    state = PositionState(quantity=10, average_cost=100.0)
    state = PositionEngine.apply(
        state, symbol="AAPL", transaction_type=TransactionType.SELL, quantity=4, price=150.0, fees=0.0
    )
    assert state.quantity == 6
    assert state.average_cost == pytest.approx(100.0)  # unchanged for remaining shares
    assert state.realized_pnl == pytest.approx((150.0 - 100.0) * 4)


def test_sell_full_position_resets_average_cost():
    state = PositionState(quantity=10, average_cost=100.0)
    state = PositionEngine.apply(
        state, symbol="AAPL", transaction_type=TransactionType.SELL, quantity=10, price=120.0, fees=0.0
    )
    assert state.quantity == 0
    assert state.average_cost == 0.0


def test_sell_more_than_held_raises():
    state = PositionState(quantity=5, average_cost=100.0)
    with pytest.raises(InsufficientHoldingQuantityError):
        PositionEngine.apply(
            state, symbol="AAPL", transaction_type=TransactionType.SELL, quantity=10, price=100.0
        )


def test_dividend_does_not_change_position():
    state = PositionState(quantity=10, average_cost=100.0)
    state = PositionEngine.apply(
        state, symbol="AAPL", transaction_type=TransactionType.DIVIDEND, quantity=0, price=25.0
    )
    assert state.quantity == 10
    assert state.average_cost == pytest.approx(100.0)


def test_bonus_shares_dilute_average_cost():
    state = PositionState(quantity=10, average_cost=100.0)  # invested = 1000
    state = PositionEngine.apply(
        state, symbol="AAPL", transaction_type=TransactionType.BONUS, quantity=10, price=0.0
    )
    assert state.quantity == 20
    assert state.average_cost == pytest.approx(50.0)  # 1000 / 20


def test_split_adjusts_quantity_and_cost_proportionally():
    state = PositionState(quantity=10, average_cost=100.0)
    state = PositionEngine.apply(
        state,
        symbol="AAPL",
        transaction_type=TransactionType.SPLIT,
        quantity=0,
        price=0.0,
        split_ratio_from=1,
        split_ratio_to=2,
    )
    assert state.quantity == pytest.approx(20.0)
    assert state.average_cost == pytest.approx(50.0)


def test_split_without_ratios_raises():
    state = PositionState(quantity=10, average_cost=100.0)
    with pytest.raises(InvalidTransactionError):
        PositionEngine.apply(state, symbol="AAPL", transaction_type=TransactionType.SPLIT, quantity=0, price=0.0)


def test_negative_quantity_raises():
    state = PositionState()
    with pytest.raises(InvalidTransactionError):
        PositionEngine.apply(
            state, symbol="AAPL", transaction_type=TransactionType.BUY, quantity=-5, price=100.0
        )
