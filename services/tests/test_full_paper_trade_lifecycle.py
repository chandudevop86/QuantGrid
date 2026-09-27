from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from test_sqlalchemy_trading_stores import configure_sqlalchemy_store


START = datetime(2026, 5, 29, 9, 15, tzinfo=timezone.utc)


def _candles(values: list[tuple[float, float, float, float, float]], minutes: int) -> list[dict]:
    return [
        {
            "timestamp": (START + timedelta(minutes=index * minutes)).isoformat(),
            "open": open_price,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        }
        for index, (open_price, high, low, close, volume) in enumerate(values)
    ]


def _h4_uptrend() -> list[dict]:
    values = []
    for index in range(16):
        open_price = 100 + index * 2
        close = open_price + 1.2
        values.append(
            (
                open_price,
                close + 1.0,
                open_price - 0.8 + index * 0.3,
                close,
                1000 + index * 50,
            )
        )
    return _candles(values, 240)


def _h1_demand_pullback() -> list[dict]:
    values = [
        (108 - index, 109 - index, 104 - index, 105 - index, 1000)
        for index in range(8)
    ]
    values.extend(
        [
            (101.5, 103.0, 99.5, 102.8, 1600),
            (102.5, 104.0, 101.8, 103.5, 1800),
        ]
    )
    return _candles(values, 60)


def _m15_bullish_trigger() -> list[dict]:
    values = [
        (
            102 + index * 0.1,
            103 + index * 0.1,
            101.5 + index * 0.1,
            102.4 + index * 0.1,
            1000 + index * 20,
        )
        for index in range(30)
    ]
    values.extend(
        [
            (103.0, 103.4, 100.8, 101.2, 1300),
            (101.1, 104.8, 100.9, 104.5, 2200),
        ]
    )
    return _candles(values, 15)


def test_real_strategy_reaches_persisted_paper_trade_and_open_position(monkeypatch):
    configure_sqlalchemy_store(monkeypatch)

    from Backend.application import order_store, paper_trade_store, position_store
    from Backend.application.execution import execution_pipeline
    from Backend.application.signal_validation import validate_signals
    import Backend.application.signal_validation as signal_validation
    from Backend.core.database import SessionLocal
    from Backend.domain.engine.execution_engine import ExecutionEngine
    from Backend.domain.models.context import StrategyContext
    from Backend.domain.security.models import User
    from Backend.domain.strategies.mtfa import MTFAConfig, MTFAStrategy
    from Backend.infrastructure.broker.broker_client import BrokerOrderResult

    m15 = _m15_bullish_trigger()
    raw_signals = MTFAStrategy(MTFAConfig(min_score=7)).run(
        m15,
        StrategyContext(
            symbol="NIFTY",
            capital=100000,
            risk_pct=1,
            rr_ratio=2,
            params={
                "h4_candles": _h4_uptrend(),
                "h1_candles": _h1_demand_pullback(),
                "m15_candles": m15,
            },
        ),
    )
    assert raw_signals
    selected_raw = raw_signals[-1]

    validation = SimpleNamespace(
        valid=True,
        valid_for_analysis=True,
        valid_for_execution=True,
        market_status="LIVE MARKET",
        dict=lambda: {
            "valid": True,
            "valid_for_analysis": True,
            "valid_for_execution": True,
            "market_status": "LIVE MARKET",
        },
    )
    monkeypatch.setattr(signal_validation, "validate_live_candle", lambda *args, **kwargs: validation)
    monkeypatch.setattr(
        signal_validation,
        "get_price",
        lambda symbol: {"source": "dhan", "price": selected_raw.entry_price},
    )

    validation_candles = list(m15)
    validation_candles[-1] = {
        **validation_candles[-1],
        "timestamp": selected_raw.signal_time.isoformat(),
        "close": selected_raw.entry_price,
    }
    validated, source = validate_signals(
        raw_signals,
        symbol="NIFTY",
        candles=validation_candles,
        candle_source="dhan",
    )
    assert source == "live"
    assert validated
    signal = validated[0]

    monkeypatch.setattr(execution_pipeline, "_execution_qualification", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        execution_pipeline,
        "validate_order_risk",
        lambda *args, **kwargs: SimpleNamespace(
            allowed=True,
            reason="OK",
            details={"risk_engine": {"risk_score": 100, "blocked_by": [], "warnings": []}},
            to_dict=lambda: {"allowed": True, "reason": "OK"},
        ),
    )
    monkeypatch.setattr(execution_pipeline, "validate_live_candle", lambda *args, **kwargs: validation)
    monkeypatch.setattr(
        execution_pipeline,
        "decide_signal",
        lambda *args, **kwargs: SimpleNamespace(
            score=9,
            regime="TRENDING",
            to_dict=lambda: {"allowed": True, "score": 9, "regime": "TRENDING"},
        ),
    )
    monkeypatch.setattr(
        execution_pipeline,
        "evaluate_risk_gate",
        lambda *_args, **_kwargs: SimpleNamespace(allowed=True, reason="OK"),
    )
    monkeypatch.setattr(execution_pipeline, "market_aligned", lambda _signal: True)
    monkeypatch.setattr(
        execution_pipeline,
        "validate_execution_constraints",
        lambda _signal: SimpleNamespace(
            accepted=True,
            reason="OK",
            lot_size=1,
            quantity=1,
            notional=float(signal.entry_price),
            required_margin=float(signal.entry_price),
        ),
    )
    monkeypatch.setattr(
        execution_pipeline,
        "apply_order_constraints",
        lambda order, constraints, quantity: order,
    )
    monkeypatch.setattr(execution_pipeline, "requested_quantity", lambda _signal: 1)

    class FilledPaperBroker:
        async def place_order(self, order):
            return BrokerOrderResult(
                broker_order_id="PAPER-FULL-E2E-1",
                status="filled",
                symbol=order.symbol,
                side=order.side,
                quantity=order.quantity,
                price=signal.entry_price,
                confirmed=True,
            )

        async def get_order_status(self, broker_order_id):
            return BrokerOrderResult(
                broker_order_id=broker_order_id,
                status="filled",
                symbol="NIFTY",
                side=signal.side,
                quantity=1,
                price=signal.entry_price,
                confirmed=True,
            )

    with SessionLocal() as db:
        actor = User(username="paper-e2e", password_hash="hash", role="trader")
        db.add(actor)
        db.commit()
        db.refresh(actor)

        result = asyncio.run(
            execution_pipeline._submit_paper_signal(
                signal,
                engine=ExecutionEngine(),
                execution_mode="paper",
                candles_1m=validation_candles,
                candles_15m=m15,
                broker_client=FilledPaperBroker(),
                db=db,
                request=None,
                actor=actor,
            )
        )

    assert result["status"] == "paper_order_submitted"
    assert result["broker_confirmed"] is True
    assert result["broker_order_id"] == "PAPER-FULL-E2E-1"

    orders = order_store.list_orders()
    assert len(orders) == 1
    assert orders[0]["status"] == "filled"
    assert orders[0]["execution_mode"] == "paper"

    trades = paper_trade_store.list_paper_trades()
    assert len(trades) == 1
    assert trades[0]["status"] == "paper_order_submitted"
    assert trades[0]["broker_order_id"] == "PAPER-FULL-E2E-1"

    position = position_store.find_position_by_broker_order_id("PAPER-FULL-E2E-1")
    assert position is not None
    assert position["status"] == "open"
    assert position["symbol"] == "NIFTY"
    assert position["quantity"] == 1

    journal = paper_trade_store.list_trade_journal()
    assert len(journal) == 1
    assert journal[0]["source"] == "paper_trade"
    assert journal[0]["symbol"] == "NIFTY"
    assert journal[0]["quantity"] == 1
    assert journal[0]["broker_order_id"] == "PAPER-FULL-E2E-1"

    monkeypatch.setenv("QUANTGRID_PAPER_BROKERAGE_PER_ORDER", "1")
    monkeypatch.setenv("QUANTGRID_PAPER_BROKERAGE_BPS", "0")
    monkeypatch.setenv("QUANTGRID_PAPER_TAXES_BPS", "10")
    monkeypatch.setenv("QUANTGRID_PAPER_SLIPPAGE_BPS", "10")
    monkeypatch.setenv("QUANTGRID_PAPER_SPREAD_BPS", "0")

    from Backend.application import trade_exit_engine

    with SessionLocal() as db:
        actor = db.query(User).filter(User.username == "paper-e2e").one()
        exit_result = asyncio.run(
            trade_exit_engine.exit_position(
                position["id"],
                db=db,
                actor=actor,
                execution_mode="paper",
                reason="manual_exit",
                exit_price=float(signal.entry_price) + 10.0,
            )
        )

    evidence = exit_result["cost_evidence"]
    assert evidence is not None
    assert evidence["gross_pnl"] == 10.0
    assert evidence["total_costs"] > 0
    assert evidence["net_pnl"] < evidence["gross_pnl"]

    closed_trade = paper_trade_store.list_paper_trades()[0]
    assert closed_trade["status"] == "closed"
    assert closed_trade["pnl"] == evidence["net_pnl"]

    closed_journal = paper_trade_store.list_trade_journal()[0]
    assert closed_journal["status"] == "closed"
    assert closed_journal["gross_pnl"] == evidence["gross_pnl"]
    assert closed_journal["total_costs"] == evidence["total_costs"]
    assert closed_journal["net_pnl"] == evidence["net_pnl"]
    assert closed_journal["pnl"] == evidence["net_pnl"]
    assert closed_journal["exit_price"] == float(signal.entry_price) + 10.0
    assert closed_journal["closed_at"] is not None
