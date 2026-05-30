from __future__ import annotations

import asyncio

from test_sqlalchemy_trading_stores import configure_sqlalchemy_store


def test_reconciliation_updates_rejected_order_and_missing_position(monkeypatch):
    configure_sqlalchemy_store(monkeypatch)
    from Backend.application import broker_reconciliation, paper_trade_store, position_store
    from Backend.core.database import SessionLocal, init_database
    from Backend.domain.security.models import User
    from Backend.infrastructure.broker.broker_client import BrokerOrderResult

    init_database()
    paper_trade_store.create_paper_trade(
        {
            "strategy": "breakout",
            "symbol": "NIFTY",
            "side": "BUY",
            "entry": 100,
            "stop_loss": 95,
            "target": 110,
            "status": "live_order_submitted",
            "broker_order_id": "REJECTED-1",
        }
    )
    paper_trade_store.create_paper_trade(
        {
            "strategy": "breakout",
            "symbol": "BANKNIFTY",
            "side": "BUY",
            "entry": 200,
            "stop_loss": 190,
            "target": 230,
            "status": "live_order_submitted",
            "broker_order_id": "FILLED-1",
        }
    )

    class FakeBroker:
        async def get_positions(self):
            return [{"tradingSymbol": "BANKNIFTY", "transactionType": "BUY", "netQty": 10, "averagePrice": 201}]

        async def get_order_status(self, broker_order_id):
            if broker_order_id == "REJECTED-1":
                return BrokerOrderResult(
                    broker_order_id=broker_order_id,
                    status="rejected",
                    symbol="NIFTY",
                    side="BUY",
                    quantity=25,
                    price=100,
                    metadata={"raw_safe": {"orderStatus": "REJECTED"}},
                )
            return BrokerOrderResult(
                broker_order_id=broker_order_id,
                status="filled",
                symbol="BANKNIFTY",
                side="BUY",
                quantity=10,
                price=201,
                confirmed=True,
                metadata={"raw_safe": {"orderStatus": "TRADED"}},
            )

    with SessionLocal() as db:
        actor = User(username="ops", password_hash="hash", role="ops")
        db.add(actor)
        db.commit()
        db.refresh(actor)
        summary = asyncio.run(broker_reconciliation.reconcile_broker_state(db=db, broker_client=FakeBroker(), actor=actor))

    assert summary["checked_orders"] == 2
    assert summary["mismatches"] == 2
    assert summary["fixed"] == 2
    rejected = [trade for trade in paper_trade_store.list_paper_trades() if trade["broker_order_id"] == "REJECTED-1"][0]
    assert rejected["status"] == "broker_rejected"
    assert rejected["broker_status"] == "rejected"
    assert rejected["raw_safe_broker_response"]["orderStatus"] == "REJECTED"
    created_position = position_store.find_position_by_broker_order_id("FILLED-1")
    assert created_position is not None
    assert created_position["quantity"] == 10


def test_reconciliation_fixes_quantity_and_price_mismatch(monkeypatch):
    configure_sqlalchemy_store(monkeypatch)
    from Backend.application import broker_reconciliation, position_store
    from Backend.core.database import SessionLocal, init_database
    from Backend.domain.security.models import User
    from Backend.infrastructure.broker.broker_client import BrokerOrderResult

    init_database()
    position_store.create_open_position(
        {
            "broker_order_id": "OPEN-1",
            "symbol": "NIFTY",
            "side": "BUY",
            "quantity": 1,
            "entry_price": 100,
        }
    )

    class FakeBroker:
        async def get_positions(self):
            return [{"tradingSymbol": "NIFTY", "transactionType": "BUY", "netQty": 3, "averagePrice": 105}]

        async def get_order_status(self, broker_order_id):
            return BrokerOrderResult(
                broker_order_id=broker_order_id,
                status="open",
                symbol="NIFTY",
                side="BUY",
                quantity=3,
                price=105,
                confirmed=True,
            )

    with SessionLocal() as db:
        actor = User(username="ops", password_hash="hash", role="ops")
        db.add(actor)
        db.commit()
        db.refresh(actor)
        summary = asyncio.run(broker_reconciliation.reconcile_broker_state(db=db, broker_client=FakeBroker(), actor=actor))

    assert summary["mismatches"] == 1
    position = position_store.find_position_by_broker_order_id("OPEN-1")
    assert position["quantity"] == 3
    assert position["entry_price"] == 105
