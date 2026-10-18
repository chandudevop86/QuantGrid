"""Durable protection-failure episode records.

The database migration owns table creation.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import Column, DateTime, Index, String, text
from sqlalchemy.orm import Session

from Backend.core.database import Base


class ProtectionAlertEpisode(Base):
    __tablename__ = "protection_alert_episodes"

    __table_args__ = (
        Index(
            "uq_protection_alert_active_order",
            "local_order_id",
            unique=True,
            sqlite_where=text("closed_at IS NULL"),
            postgresql_where=text("closed_at IS NULL"),
        ),
    )

    episode_id = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )

    local_order_id = Column(
        String(120),
        nullable=False,
    )

    opened_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )

    closed_at = Column(
        DateTime,
        nullable=True,
    )



def open_protection_failure_episode(
    db: Session,
    *,
    local_order_id: str,
) -> str:
    """Open or reuse an active episode without committing."""
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert

    if not isinstance(local_order_id, str) or not local_order_id.strip():
        raise ValueError("A nonempty local_order_id is required")

    dialect = db.get_bind().dialect.name
    if dialect == "postgresql":
        insert_factory = pg_insert
    elif dialect == "sqlite":
        insert_factory = sqlite_insert
    else:
        raise RuntimeError("Unsupported episode database dialect")

    # SQLite's legacy transaction handling requires a real BEGIN
    # before SAVEPOINT, so caller rollback remains effective.
    if dialect == "sqlite":
        connection = db.connection()
        raw = connection.connection.driver_connection
        if not raw.in_transaction:
            connection.exec_driver_sql("BEGIN")

    candidate = str(uuid4())

    statement = (
        insert_factory(ProtectionAlertEpisode)
        .values(
            episode_id=candidate,
            local_order_id=local_order_id,
            opened_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        .on_conflict_do_nothing(
            index_elements=["local_order_id"],
            index_where=ProtectionAlertEpisode.closed_at.is_(None),
        )
        .returning(ProtectionAlertEpisode.episode_id)
    )

    with db.begin_nested():
        inserted = db.execute(statement).scalar_one_or_none()

        if inserted is not None:
            return inserted

        existing = (
            db.query(ProtectionAlertEpisode.episode_id)
            .filter(
                ProtectionAlertEpisode.local_order_id == local_order_id,
                ProtectionAlertEpisode.closed_at.is_(None),
            )
            .scalar()
        )

        if existing is None:
            raise RuntimeError("Active protection episode not found")

        return existing


def close_protection_failure_episode(
    db: Session,
    *,
    local_order_id: str,
) -> int:
    """Close active episodes without committing."""
    from sqlalchemy import update

    if not isinstance(local_order_id, str) or not local_order_id.strip():
        raise ValueError("A nonempty local_order_id is required")

    statement = (
        update(ProtectionAlertEpisode)
        .where(
            ProtectionAlertEpisode.local_order_id == local_order_id,
            ProtectionAlertEpisode.closed_at.is_(None),
        )
        .values(
            closed_at=datetime.now(timezone.utc).replace(tzinfo=None)
        )
    )

    result = db.execute(statement)
    return result.rowcount
