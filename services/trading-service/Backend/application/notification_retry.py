from __future__ import annotations

import logging
import os
from uuid import uuid4

from datetime import UTC, datetime
from sqlalchemy.orm import Session

from Backend.application.notifications import send_notification_channel
from Backend.application.notification_store import (
    claim_notification,
    get_retry_notifications,
    mark_sent,
    mark_failed,
    schedule_retry,
)

logger = logging.getLogger(__name__)


def _safe_delivery_error(exc: Exception) -> str:
    """Return a bounded error category without provider response details."""
    if isinstance(exc, (TimeoutError, ConnectionError)):
        return "notification_delivery_network_failure"
    if isinstance(exc, (ValueError, TypeError)):
        return "notification_delivery_validation_failure"
    return "notification_delivery_provider_failure"


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
            datetime.now(UTC),
        )

        logger.info(
            "Notification retry worker started (%s notifications)",
            len(notifications),
        )

        for notification in notifications:

            notification_id = notification.id
            claim_token = uuid4().hex

            if not claim_notification(
                self.db,
                notification_id,
                claim_token,
                datetime.now(UTC),
            ):
                logger.info(
                    "Notification %s already claimed by another worker.",
                    notification_id,
                )
                continue

            processed += 1

            try:

                logger.info(
                    "Retrying notification id=%s attempt=%s",
                    notification.id,
                    getattr(notification, "retries", 0) + 1,
                )

                send_notification_channel(
                    notification.channel,
                    notification.recipient,
                    notification.subject,
                    notification.message,
                )

            except Exception as exc:

                safe_error = _safe_delivery_error(exc)
                logger.error(
                    "Notification retry failed id=%s category=%s",
                    notification.id,
                    safe_error,
                )

                retry_count = getattr(
                    notification,
                    "retries",
                    0,
                )

                try:
                    if retry_count + 1 >= self.max_retries:

                        updated = mark_failed(
                            self.db,
                            notification.id,
                            safe_error,
                            claim_token=claim_token,
                        )
                        if not updated:
                            logger.warning(
                                "Notification %s lost claim before FAILED update",
                                notification.id,
                            )
                            continue

                        self.db.commit()

                        permanently_failed += 1

                        logger.error(
                            "Notification %s permanently failed after %s retries.",
                            notification.id,
                            self.max_retries,
                        )

                    else:

                        updated = schedule_retry(
                            self.db,
                            notification.id,
                            safe_error,
                            claim_token=claim_token,
                        )
                        if not updated:
                            logger.warning(
                                "Notification %s lost claim before RETRY update",
                                notification.id,
                            )
                            continue

                        self.db.commit()

                        failed += 1
                except Exception:
                    self.db.rollback()
                    logger.error(
                        "Notification %s retry status database update failed",
                        notification_id,
                    )
                    raise
            else:
                try:
                    updated = mark_sent(
                        self.db,
                        notification.id,
                        claim_token=claim_token,
                    )
                    if not updated:
                        logger.warning(
                            "Notification %s lost claim before SENT update",
                            notification.id,
                        )
                        continue

                    self.db.commit()

                    succeeded += 1

                    logger.info(
                        "Notification %s sent successfully.",
                        notification.id,
                    )

                except Exception:
                    self.db.rollback()
                    logger.error(
                        "Notification %s delivery accepted but "
                        "database confirmation failed",
                        notification_id,
                    )
                    raise

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