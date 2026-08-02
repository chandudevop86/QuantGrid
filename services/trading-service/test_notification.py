from Backend.application.notification_service import NotificationService
from Backend.domain.events.trading_events import NotificationEventType
from Backend.domain.notifications.models import (
    NotificationChannel,
    NotificationStatus,
)


class DummyRepository:
    def save_event(self, event):
        event.id = "TEST-001"  # if your model has an id field
        return event

    def get_pending_events(self):
        return []

    def mark_sent(self, event_id):
        pass

    def mark_failed(self, event_id, reason):
        pass


def test_create_notification():
    service = NotificationService(DummyRepository())

    notification = service.create_notification(
        event_type=NotificationEventType.ORDER_FILLED,
        subject="Order Completed",
        message="NIFTY 24200 CE filled at 125",
        channel=NotificationChannel.TELEGRAM,
        order_id="ORD1001",
        symbol="NIFTY",
    )

    assert notification.subject == "Order Completed"
    assert notification.message == "NIFTY 24200 CE filled at 125"
    assert notification.event_type == NotificationEventType.ORDER_FILLED.value
    assert notification.channel == NotificationChannel.TELEGRAM
    assert notification.status == NotificationStatus.PENDING