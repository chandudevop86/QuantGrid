"""Create PostgreSQL reservation tables without enabling live execution.

Revision ID: 0009_option_live_reservations
Revises: 0008_signal_evaluation_events
"""
from alembic import op
import sqlalchemy as sa

revision = "0009_option_live_reservations"
down_revision = "0008_signal_evaluation_events"
branch_labels = None
depends_on = None


def upgrade():
    if op.get_bind().dialect.name != "postgresql":
        raise RuntimeError("PostgreSQL required for live reservation tables")
    op.create_table(
        "option_live_account_locks",
        sa.Column("broker_account_id", sa.Text(), primary_key=True),
    )
    op.create_table(
        "option_live_pg_reservations",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("broker_account_id", sa.Text(), sa.ForeignKey("option_live_account_locks.broker_account_id"), nullable=False),
        sa.Column("actor_id", sa.Text(), nullable=False),
        sa.Column("idem_key", sa.Text(), nullable=False),
        sa.Column("premium_rupees", sa.Numeric(14, 2), nullable=False),
        sa.Column("state", sa.Text(), nullable=False),
        sa.CheckConstraint("premium_rupees > 0", name="ck_option_live_pg_positive_premium"),
        sa.CheckConstraint("state IN ('reserved','submitted','unknown','filled','released')", name="ck_option_live_pg_state"),
        sa.UniqueConstraint("broker_account_id", "actor_id", "idem_key", name="uq_option_live_pg_idempotency"),
    )
    op.create_index("option_live_pg_active_account_idx", "option_live_pg_reservations", ["broker_account_id", "state"])
    op.create_table(
        "option_live_pg_order_bindings",
        sa.Column("reservation_id", sa.BigInteger(), sa.ForeignKey("option_live_pg_reservations.id"), primary_key=True),
        sa.Column("broker_account_id", sa.Text(), sa.ForeignKey("option_live_account_locks.broker_account_id"), nullable=False),
        sa.Column("broker_order_id", sa.Text(), nullable=False),
        sa.Column("security_id", sa.Text(), nullable=False),
        sa.UniqueConstraint("broker_account_id", "broker_order_id", name="uq_option_live_pg_broker_order"),
    )


def downgrade():
    raise RuntimeError("Live reservation evidence cannot be dropped automatically")
