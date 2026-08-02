from Backend.domain.notifications.models import (
    NotificationEvent,
    NotificationChannel,
    NotificationStatus,
)

from Backend.domain.events.trading_events import NotificationEventType


class NotificationService:


    def __init__(
        self,
        repository
    ):
        self.repository = repository



    def create_notification(
        self,
        *,
        event_type: NotificationEventType,
        subject: str,
        message: str,
        channel: NotificationChannel = NotificationChannel.TELEGRAM,
        order_id: str | None = None,
        symbol: str | None = None,
        payload: dict | None = None,
    ) -> NotificationEvent:


        event = NotificationEvent(

            event_type=event_type.value,

            subject=subject,

            message=message,

            channel=channel,

            status=NotificationStatus.PENDING,

        )


        saved_event = self.repository.save_event(event)


        return saved_event



    def send_pending_notifications(self):

        events = self.repository.get_pending_events()


        for event in events:

            try:

                self.send(event)

                self.repository.mark_sent(
                    event.id
                )


            except Exception as error:

                self.repository.mark_failed(
                    event.id,
                    str(error)
                )



    def send(
        self,
        event: NotificationEvent
    ):

        """
        Future integration:
        Telegram
        Email
        Slack
        """

        print(
            f"Sending {event.channel}: {event.message}"
        )