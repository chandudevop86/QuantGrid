"""Normalize paper trade and trade journal timestamps.

Existing deployments created these tables outside Alembic with VARCHAR
timestamp columns. Convert the existing values to PostgreSQL TIMESTAMPTZ
while preserving all existing rows.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0006_paper_trade_timestamps"
down_revision = "0005_datasets"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Empty legacy strings are semantically NULL and cannot be cast directly
    # to timestamptz.
    op.execute(
        sa.text(
            """
            UPDATE paper_trades
            SET signal_time = NULL
            WHERE NULLIF(TRIM(signal_time), '') IS NULL
            """
        )
    )

    op.execute(
        sa.text(
            """
            UPDATE trade_journal
            SET closed_at = NULL
            WHERE NULLIF(TRIM(closed_at), '') IS NULL
            """
        )
    )

    # Existing values were already validated before this migration:
    # ISO-8601 timestamps with explicit timezone offsets.
    op.alter_column(
        "paper_trades",
        "signal_time",
        existing_type=sa.String(length=40),
        type_=sa.DateTime(timezone=True),
        existing_nullable=True,
        postgresql_using="NULLIF(TRIM(signal_time), '')::timestamptz",
    )

    op.alter_column(
        "paper_trades",
        "created_at",
        existing_type=sa.String(length=40),
        type_=sa.DateTime(timezone=True),
        existing_nullable=False,
        postgresql_using="created_at::timestamptz",
    )

    op.alter_column(
        "trade_journal",
        "created_at",
        existing_type=sa.String(length=40),
        type_=sa.DateTime(timezone=True),
        existing_nullable=False,
        postgresql_using="created_at::timestamptz",
    )

    op.alter_column(
        "trade_journal",
        "closed_at",
        existing_type=sa.String(length=40),
        type_=sa.DateTime(timezone=True),
        existing_nullable=True,
        postgresql_using="NULLIF(TRIM(closed_at), '')::timestamptz",
    )


def downgrade() -> None:
    # Convert timestamps back to ISO-8601 strings.
    op.alter_column(
        "paper_trades",
        "signal_time",
        existing_type=sa.DateTime(timezone=True),
        type_=sa.String(length=40),
        existing_nullable=True,
        postgresql_using="signal_time::text",
    )

    op.alter_column(
        "paper_trades",
        "created_at",
        existing_type=sa.DateTime(timezone=True),
        type_=sa.String(length=40),
        existing_nullable=False,
        postgresql_using="created_at::text",
    )

    op.alter_column(
        "trade_journal",
        "created_at",
        existing_type=sa.DateTime(timezone=True),
        type_=sa.String(length=40),
        existing_nullable=False,
        postgresql_using="created_at::text",
    )

    op.alter_column(
        "trade_journal",
        "closed_at",
        existing_type=sa.DateTime(timezone=True),
        type_=sa.String(length=40),
        existing_nullable=True,
        postgresql_using="closed_at::text",
    )
