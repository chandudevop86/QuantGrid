"""Create append-only signal evaluation event store.

Revision ID: 0008_signal_evaluation_events
Revises: 0007_paper_trade_cost_evidence
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0008_signal_evaluation_events"
down_revision = "0007_paper_trade_cost_evidence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "signal_evaluation_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("evaluation_id", sa.String(64), nullable=False),
        sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column("signal_id", sa.String(64), nullable=False),
        sa.Column("strategy", sa.String(80), nullable=False),
        sa.Column("symbol", sa.String(32), nullable=False),
        sa.Column("side", sa.String(20), nullable=False),
        sa.Column("signal_time", sa.String(64), nullable=False),
        sa.Column("snapshot_time", sa.String(64), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("reason", sa.String(80), nullable=False),
        sa.Column("mtf_bias", sa.String(40), nullable=False),
        sa.Column("evidence_json", sa.Text(), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("evaluation_id", "event_type", name="uq_signal_eval_event"),
    )


def downgrade() -> None:
    op.drop_table("signal_evaluation_events")
