from datetime import datetime
from typing import Optional, List

from Backend.domain.notifications.models import (
    NotificationEvent,
    NotificationStatus,
    NotificationChannel,
)

from Backend.domain.notifications.repository import (
    NotificationRepository
)


class PostgresNotificationRepository(NotificationRepository):


    def __init__(self, db):
        self.db = db



    def save_event(
        self,
        event: NotificationEvent
    ) -> NotificationEvent:

        query = """
        INSERT INTO notification_events
        (
            event_type,
            subject,
            message,
            channel,
            status,
            error,
            created_at,
            sent_at
        )

        VALUES
        (
            %s,%s,%s,%s,%s,%s,%s,%s
        )

        RETURNING id;
        """

        result = self.db.execute(
            query,
            (
                event.event_type,
                event.subject,
                event.message,
                event.channel.value,
                event.status.value,
                event.error,
                event.created_at,
                event.sent_at,
            )
        )

        event.id = result.fetchone()[0]

        return event



    def get_pending_events(
        self,
        limit: int = 100
    ) -> List[NotificationEvent]:

        query = """
        SELECT
            id,
            event_type,
            subject,
            message,
            channel,
            status,
            error,
            created_at,
            sent_at

        FROM notification_events

        WHERE status='PENDING'

        ORDER BY created_at ASC

        LIMIT %s;
        """

        rows = self.db.execute(
            query,
            (limit,)
        ).fetchall()


        events = []

        for row in rows:

            events.append(
                NotificationEvent(

                    id=row[0],

                    event_type=row[1],

                    subject=row[2],

                    message=row[3],

                    channel=NotificationChannel(row[4]),

                    status=NotificationStatus(row[5]),

                    error=row[6],

                    created_at=row[7],

                    sent_at=row[8],
                )
            )

        return events



    def mark_sent(
        self,
        event_id: int
    ) -> None:

        query = """
        UPDATE notification_events

        SET
            status='SENT',
            sent_at=%s

        WHERE id=%s;
        """

        self.db.execute(
            query,
            (
                datetime.utcnow(),
                event_id
            )
        )



    def mark_failed(
        self,
        event_id: int,
        error: str
    ) -> None:

        query = """
        UPDATE notification_events

        SET
            status='FAILED',
            error=%s

        WHERE id=%s;
        """

        self.db.execute(
            query,
            (
                error,
                event_id
            )
        )



    def get_by_id(
        self,
        event_id: int
    ) -> Optional[NotificationEvent]:

        query = """
        SELECT *
        FROM notification_events
        WHERE id=%s;
        """

        row = self.db.execute(
            query,
            (event_id,)
        ).fetchone()


        if not row:
            return None


        return NotificationEvent(

            id=row[0],
            event_type=row[1],
            subject=row[2],
            message=row[3],
            channel=NotificationChannel(row[4]),
            status=NotificationStatus(row[5]),
            error=row[6],
            created_at=row[7],
            sent_at=row[8],
        )