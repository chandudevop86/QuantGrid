"""Persist immutable content-addressed market dataset snapshots."""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0005_dataset_snapshots"
down_revision = "0004_strategy_version_reproducibility"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dataset_snapshots",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("provider", sa.String(80), nullable=False),
        sa.Column("exchange", sa.String(40), nullable=False),
        sa.Column("security_identifier", sa.String(120), nullable=False),
        sa.Column("symbol", sa.String(64), nullable=False),
        sa.Column("instrument", sa.String(80), nullable=False),
        sa.Column("timeframe", sa.String(32), nullable=False),
        sa.Column("timezone", sa.String(80), nullable=False),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("dataset_hash", sa.String(64), nullable=False),
        sa.Column("source_metadata_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("provider", "exchange", "security_identifier", "instrument", "timeframe", "dataset_hash", "source_metadata_hash", name="uq_dataset_snapshot_content"),
    )
    op.create_index("ix_dataset_snapshots_dataset_hash", "dataset_snapshots", ["dataset_hash"])
    op.create_index("ix_dataset_snapshots_symbol_timeframe", "dataset_snapshots", ["symbol", "timeframe"])


def downgrade() -> None:
    op.drop_table("dataset_snapshots")
