"""LIVE protection alert lifecycle through simulated reconciliation."""

import asyncio

from test_broker_reconciliation import configure_sqlalchemy_store


def test_live_protection_failure_recovery_and_recurrence(monkeypatch):
    configure_sqlalchemy_store(monkeypatch)

    from Backend.application import broker_reconciliation, order_store
    from Backend.application.notification_entity import NotificationEntity
    from Backend.application.protection_alert_episodes import ProtectionAlertEpisode
    from Backend.core.database import SessionLocal, init_database
    from Backend.domain.security.models import User
    from Backend.infrastructure.broker.broker_client import BrokerOrderResult

    monkeypatch.setenv("QUANTGRID_ALERTS_ENABLED", "true")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "test-chat")

    init_database()

    local_id = "ORD-LIVE-EPISODE-LIFECYCLE"
    broker_id = "DHAN-LIVE-EPISODE-LIFECYCLE"

    order_store.create_order({
        "local_order_id": local_id,
        "broker_order_id": broker_id,
        "order_key": "NIFTY:BUY:EPISODE-LIFECYCLE",
        "symbol": "NIFTY",
        "side": "BUY",
        "quantity": 25,
        "entry_price": 100,
        "execution_mode": "live",
        "status": "broker_submitted",
    })

    class SimulatedBroker:
        state = "unprotected"

        async def get_positions(self):
            return [{
                "tradingSymbol": "NIFTY",
                "transactionType": "BUY",
                "netQty": 25,
                "averagePrice": 100,
            }]

        async def get_order_status(self, requested):
            assert requested == broker_id
            if self.state == "unavailable":
                raise RuntimeError("simulated broker outage")
            return BrokerOrderResult(
                broker_order_id=broker_id,
                status="filled",
                symbol="NIFTY",
                side="BUY",
                quantity=25,
                filled_quantity=25,
                remaining_quantity=0,
                price=100,
                confirmed=True,
            )

        async def get_super_order_status(self, requested):
            assert requested == broker_id
            protected = self.state == "protected"
            return BrokerOrderResult(
                broker_order_id=broker_id,
                status="filled",
                symbol="NIFTY",
                side="BUY",
                quantity=25,
                filled_quantity=25,
                remaining_quantity=0,
                price=100,
                confirmed=True,
                metadata={
                    "super_order": {
                        "legs": {
                            "STOP_LOSS_LEG": {
                                "quantity": 25 if protected else 0,
                                "remaining_quantity": 25 if protected else 0,
                                "status": "open" if protected else "missing",
                            }
                        },
                        "protection": {
                            "protected": protected,
                            "stop_loss_present": protected,
                            "stop_loss_active": protected,
                            "exposed_quantity": 25,
                        },
                    }
                },
            )

    broker = SimulatedBroker()

    with SessionLocal() as db:
        actor = User(
            username="episode-lifecycle-ops",
            password_hash="hash",
            role="ops",
        )
        db.add(actor)
        db.commit()
        db.refresh(actor)

        def reconcile():
            return asyncio.run(
                broker_reconciliation.reconcile_broker_state(
                    db=db,
                    broker_client=broker,
                    actor=actor,
                    execution_mode="live",
                )
            )

        def snapshot():
            with SessionLocal() as check_db:
                episodes = (
                    check_db.query(ProtectionAlertEpisode)
                    .filter(ProtectionAlertEpisode.local_order_id == local_id)
                    .order_by(ProtectionAlertEpisode.opened_at)
                    .all()
                )
                notifications = (
                    check_db.query(NotificationEntity)
                    .filter(
                        NotificationEntity.channel == "telegram",
                        NotificationEntity.subject.like(
                            "%LIVE position protection failure%"
                        ),
                    )
                    .all()
                )
                return [
                    (episode.episode_id, episode.closed_at)
                    for episode in episodes
                ], len(notifications)

        # First failure opens an episode and enqueues an alert.
        assert reconcile()["needs_review"] >= 1
        episodes, count = snapshot()
        assert len(episodes) == 1
        assert episodes[0][1] is None
        assert count == 1
        first_episode_id = episodes[0][0]

        # Repeated failure must not enqueue a duplicate.
        assert reconcile()["needs_review"] >= 1
        episodes, count = snapshot()
        assert len(episodes) == 1
        assert episodes[0][0] == first_episode_id
        assert count == 1

        # Unavailable broker evidence must not close the episode.
        broker.state = "unavailable"
        reconcile()
        episodes, count = snapshot()
        assert len(episodes) == 1
        assert episodes[0][1] is None
        assert count == 1

        # Verified active stop-loss coverage closes the episode.
        broker.state = "protected"
        reconcile()
        episodes, count = snapshot()
        assert len(episodes) == 1
        assert episodes[0][1] is not None
        assert count == 1

        # A new protection failure opens a distinct episode and alert.
        broker.state = "unprotected"
        assert reconcile()["needs_review"] >= 1
        episodes, count = snapshot()
        assert len(episodes) == 2
        assert episodes[0][0] != episodes[1][0]
        assert sum(closed is None for _, closed in episodes) == 1
        assert count == 2
