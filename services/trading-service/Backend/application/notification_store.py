from __future__ import annotations

import os

from datetime import UTC, datetime, timedelta, timezone

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session


from Backend.application.notification_entity import (
    NotificationEntity,
)



DEFAULT_RETRY_INTERVAL = int(
    os.getenv(
        "QUANTGRID_NOTIFICATION_RETRY_INTERVAL_SECONDS",
        "60",
    )
)


def create_notification(
    db: Session,
    *,
    channel: str,
    subject: str,
    message: str,
    recipient: str,
):

    obj = NotificationEntity(
        channel=channel,
        subject=subject,
        message=message,
        recipient=recipient,
        status="PENDING",
        retries=0,
        delivered=False,
        next_retry_at=None,
        error=None,
    )

    db.add(obj)
    db.commit()
    db.refresh(obj)

    return obj




def enqueue_notifications_atomic(
    db: Session,
    *,
    destinations: list[tuple[str, str]],
    subject: str,
    message: str,
    incident_key: str,
) -> int:
    """Stage an atomic, duplicate-safe notification batch.

    The caller owns the outer transaction and must commit it.
    """
    import hashlib
    import json

    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert

    if not isinstance(incident_key, str) or not incident_key.strip():
        raise ValueError("A nonempty incident_key is required")

    if not destinations:
        raise ValueError("At least one destination is required")

    validated = []

    for channel, recipient in destinations:
        if channel not in {"telegram", "slack", "email"}:
            raise ValueError("Unsupported notification channel")

        if not isinstance(recipient, str) or not recipient.strip():
            raise ValueError("A nonempty recipient is required")

        if channel == "slack" and recipient != "configured":
            raise ValueError("Slack recipient must be 'configured'")

        validated.append((channel, recipient))

    dialect = db.get_bind().dialect.name

    if dialect == "postgresql":
        insert_factory = pg_insert
    elif dialect == "sqlite":
        insert_factory = sqlite_insert
    else:
        raise RuntimeError("Unsupported notification database dialect")

    # Python's sqlite3 legacy transaction handling can create a
    # SAVEPOINT before a real outer BEGIN. Releasing that SAVEPOINT
    # would make the inserts survive a later Session.rollback().
    # Start the real SQLite transaction first when necessary.
    if dialect == "sqlite":
        connection = db.connection()
        raw_connection = connection.connection.driver_connection
        if not raw_connection.in_transaction:
            connection.exec_driver_sql("BEGIN")

    inserted = 0

    with db.begin_nested():
        for channel, recipient in validated:
            digest = hashlib.sha256(
                json.dumps(
                    [incident_key, channel, recipient],
                    ensure_ascii=False,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()

            statement = insert_factory(NotificationEntity).values(
                channel=channel,
                recipient=recipient,
                subject=subject,
                message=message,
                dedup_key="critical:" + digest,
                status="PENDING",
                retries=0,
                delivered=False,
            ).on_conflict_do_nothing(
                index_elements=["dedup_key"]
            ).returning(NotificationEntity.id)

            result = db.execute(statement)
            inserted += len(result.all())

    return inserted

def _utc_naive(value: datetime) -> datetime:
    """Normalize timestamps to UTC-naive database values."""
    if value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)

def mark_sent(
    db: Session,
    notification_id: int,
    *,
    claim_token: str,
) -> bool:
    """Mark delivered only if the caller owns the active claim."""
    if not claim_token:
        raise ValueError("claim_token is required")

    result = (
        db.query(NotificationEntity)
        .filter(
            NotificationEntity.id == notification_id,
            NotificationEntity.status == "PROCESSING",
            NotificationEntity.claim_token == claim_token,
            NotificationEntity.lease_expires_at > datetime.now(UTC).replace(tzinfo=None),
        )
        .update(
            {
                NotificationEntity.status: "SENT",
                NotificationEntity.sent_at: datetime.now(UTC).replace(tzinfo=None),
                NotificationEntity.delivered: True,
                NotificationEntity.error: None,
                NotificationEntity.next_retry_at: None,
                NotificationEntity.claim_token: None,
                NotificationEntity.lease_expires_at: None,
            },
            synchronize_session=False,
        )
    )

    db.commit()
    db.expire_all()
    return result == 1


def mark_failed(
    db: Session,
    notification_id: int,
    error: str,
    *,
    claim_token: str,
) -> bool:
    """Fail only a notification owned by the active claimant."""
    if not claim_token:
        raise ValueError("claim_token is required")

    now = datetime.now(UTC).replace(tzinfo=None)

    result = (
        db.query(NotificationEntity)
        .filter(
            NotificationEntity.id == notification_id,
            NotificationEntity.status == "PROCESSING",
            NotificationEntity.claim_token == claim_token,
            NotificationEntity.lease_expires_at > now,
        )
        .update(
            {
                NotificationEntity.status: "FAILED",
                NotificationEntity.error: error,
                NotificationEntity.delivered: False,
                NotificationEntity.next_retry_at: None,
                NotificationEntity.claim_token: None,
                NotificationEntity.lease_expires_at: None,
            },
            synchronize_session=False,
        )
    )

    db.commit()
    db.expire_all()
    return result == 1


def schedule_retry(
    db: Session,
    notification_id: int,
    error: str,
    *,
    claim_token: str,
) -> bool:
    """Schedule retry only for the active claim owner."""
    if not claim_token:
        raise ValueError("claim_token is required")

    now = datetime.now(UTC).replace(tzinfo=None)

    result = (
        db.query(NotificationEntity)
        .filter(
            NotificationEntity.id == notification_id,
            NotificationEntity.status == "PROCESSING",
            NotificationEntity.claim_token == claim_token,
            NotificationEntity.lease_expires_at > now,
        )
        .update(
            {
                NotificationEntity.status: "RETRY",
                NotificationEntity.error: error,
                NotificationEntity.delivered: False,
                NotificationEntity.retries: NotificationEntity.retries + 1,
                NotificationEntity.next_retry_at: (
                    now + timedelta(seconds=DEFAULT_RETRY_INTERVAL)
                ),
                NotificationEntity.claim_token: None,
                NotificationEntity.lease_expires_at: None,
            },
            synchronize_session=False,
        )
    )

    db.commit()
    db.expire_all()
    return result == 1


def get_retry_notifications(
    db: Session,
    now: datetime,
):

    return (
        db.query(NotificationEntity)
        .filter(
            or_(
                NotificationEntity.status == "PENDING",
                and_(
                    NotificationEntity.status == "RETRY",
                    NotificationEntity.next_retry_at <= now,
                ),
                and_(
                    NotificationEntity.status == "PROCESSING",
                    NotificationEntity.lease_expires_at <= now,
                ),
            )
        )
        .all()
    )

def claim_notification(
    db: Session,
    notification_id: int,
    claim_token: str,
    now: datetime,
    lease_seconds: int = 120,
) -> bool:
    """Atomically claim a pending, due, or expired notification."""
    now = _utc_naive(now)

    now = _utc_naive(now)

    if not claim_token or lease_seconds <= 0:
        raise ValueError("A claim token and positive lease are required")

    eligible = or_(
        NotificationEntity.status == "PENDING",
        and_(
            NotificationEntity.status == "RETRY",
            NotificationEntity.next_retry_at <= now,
        ),
        and_(
            NotificationEntity.status == "PROCESSING",
            NotificationEntity.lease_expires_at <= now,
        ),
    )

    result = (
        db.query(NotificationEntity)
        .filter(
            NotificationEntity.id == notification_id,
            eligible,
        )
        .update(
            {
                NotificationEntity.status: "PROCESSING",
                NotificationEntity.claim_token: claim_token,
                NotificationEntity.lease_expires_at: (
                    now + timedelta(seconds=lease_seconds)
                ),
            },
            synchronize_session=False,
        )
    )

    db.commit()
    db.expire_all()
    return result == 1
