from __future__ import annotations

import logging
import os

from datetime import datetime
from sqlalchemy.orm import Session

from Backend.application.notifications import send_alert
from Backend.application.notification_store import (
    get_retry_notifications,
    mark_sent,
    mark_failed,
    schedule_retry,
)

logger = logging.getLogger(__name__)


class NotificationRetryWorker:
    """
    Periodically retries failed notifications.

    Flow
    ----
    Pending Notification
            │
            ▼
        send_alert()
        │        │
        │        ├──────── Success
        │        │              ▼
        │        │        mark_sent()
        │        │
        │        └──────── Failure
        │
        ▼
    retry_count >= MAX ?
        │
        ├── No
        │      ▼
        │ schedule_retry()
        │
        └── Yes
               ▼
         mark_failed()
    """

    DEFAULT_MAX_RETRIES = 5

    def __init__(self, db: Session):
        self.db = db

        self.max_retries = int(
            os.getenv(
                "QUANTGRID_NOTIFICATION_MAX_RETRIES",
                self.DEFAULT_MAX_RETRIES,
            )
        )

    async def run(self) -> dict:

        processed = 0
        succeeded = 0
        failed = 0
        permanently_failed = 0

        notifications = get_retry_notifications(
            self.db,
            datetime.utcnow(),
        )

        logger.info(
            "Notification retry worker started (%s notifications)",
            len(notifications),
        )

        for notification in notifications:

            processed += 1

            try:

                logger.info(
                    "Retrying notification id=%s attempt=%s",
                    notification.id,
                    getattr(notification, "retry_count", 0) + 1,
                )

                send_alert(
                    notification.subject,
                    notification.message,
                )

                mark_sent(
                    self.db,
                    notification.id,
                )

                self.db.commit()

                succeeded += 1

                logger.info(
                    "Notification %s sent successfully.",
                    notification.id,
                )

            except Exception as exc:

                logger.exception(
                    "Notification retry failed id=%s",
                    notification.id,
                )

                retry_count = getattr(
                    notification,
                    "retry_count",
                    0,
                )

                if retry_count + 1 >= self.max_retries:

                    mark_failed(
                        self.db,
                        notification.id,
                        str(exc),
                    )

                    self.db.commit()

                    permanently_failed += 1

                    logger.error(
                        "Notification %s permanently failed after %s retries.",
                        notification.id,
                        self.max_retries,
                    )

                else:

                    schedule_retry(
                        self.db,
                        notification.id,
                        str(exc),
                    )

                    self.db.commit()

                    failed += 1

        logger.info(
            "Notification retry finished "
            "(processed=%s succeeded=%s retry_scheduled=%s permanently_failed=%s)",
            processed,
            succeeded,
            failed,
            permanently_failed,
        )

        return {
            "processed": processed,
            "succeeded": succeeded,
            "retry_scheduled": failed,
            "permanently_failed": permanently_failed,
            "max_retries": self.max_retries,
        }