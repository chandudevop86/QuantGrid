from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

from Backend.domain.models.signal import StrategySignal
from Backend.trading_system.broker import MockBroker
from Backend.trading_system.execution import ExecutionEngine
from Backend.trading_system.risk import GlobalRiskConfig, GlobalRiskManager


def _signal(**overrides):
    values = {
        "strategy_name": "central-risk",
        "symbol": "NIFTY",
        "side": "BUY",
        "entry_price": 100.0,
        "stop_loss": 95.0,
        "target_price": 110.0,
        "signal_time": datetime.utcnow(),
        "metadata": {"score": 20, "risk_pct": 1.0},
    }
    values.update(overrides)
    return StrategySignal(**values)


def test_central_risk_rejects_max_daily_loss_before_broker():
    manager = GlobalRiskManager(GlobalRiskConfig(max_daily_loss_pct=1.0))
    manager.daily_pnl[datetime.utcnow().date()] = -2_000
    broker = MockBroker()

    result = asyncio.run(ExecutionEngine(broker=broker, risk_manager=manager).execute_signal(_signal(), market_price=100))

    assert result.reason == "max_daily_loss_exceeded"
    assert broker.orders == {}


def test_central_risk_rejects_max_trades_per_day_before_broker():
    manager = GlobalRiskManager(GlobalRiskConfig(max_trades_per_day=1))
    manager.daily_trades[datetime.utcnow().date()] = 1
    broker = MockBroker()

    result = asyncio.run(ExecutionEngine(broker=broker, risk_manager=manager).execute_signal(_signal(), market_price=100))

    assert result.reason == "max_trades_per_day_exceeded"
    assert broker.orders == {}


def test_central_risk_rejects_stale_signal_before_broker():
    manager = GlobalRiskManager(GlobalRiskConfig(max_stale_seconds=60))
    broker = MockBroker()

    result = asyncio.run(
        ExecutionEngine(broker=broker, risk_manager=manager).execute_signal(
            _signal(signal_time=datetime.utcnow() - timedelta(seconds=120)),
            market_price=100,
        )
    )

    assert result.reason == "stale_signal"
    assert broker.orders == {}


def test_central_risk_rejects_minimum_score_before_broker():
    manager = GlobalRiskManager(GlobalRiskConfig(min_signal_score=10))
    broker = MockBroker()

    result = asyncio.run(
        ExecutionEngine(broker=broker, risk_manager=manager).execute_signal(
            _signal(metadata={"score": 5, "risk_pct": 1.0}),
            market_price=100,
        )
    )

    assert result.reason == "signal_score_below_threshold"
    assert broker.orders == {}


def test_central_risk_position_sizing_controls_order_quantity():
    manager = GlobalRiskManager(GlobalRiskConfig(starting_equity=100_000))
    broker = MockBroker()

    result = asyncio.run(
        ExecutionEngine(broker=broker, risk_manager=manager).execute_signal(
            _signal(metadata={"score": 20, "risk_pct": 1.0, "lot_size": 5}),
            market_price=100,
        )
    )

    assert result.accepted is True
    assert result.order is not None
    assert result.order.qty == 200
    assert result.metadata["risk_decision"]["risk_per_unit"] == 5.0
