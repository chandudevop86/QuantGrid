"""Add cost-adjusted paper trade journal evidence fields."""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0007_paper_trade_cost_evidence"
down_revision = "0006_paper_trade_timestamps"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("trade_journal", sa.Column("gross_pnl", sa.Float(), nullable=True))
    op.add_column("trade_journal", sa.Column("total_costs", sa.Float(), nullable=True))
    op.add_column("trade_journal", sa.Column("net_pnl", sa.Float(), nullable=True))
    op.add_column("trade_journal", sa.Column("broker_order_id", sa.String(length=120), nullable=True))
    op.create_index(
        "ix_trade_journal_broker_order_id",
        "trade_journal",
        ["broker_order_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_trade_journal_broker_order_id", table_name="trade_journal")
    op.drop_column("trade_journal", "broker_order_id")
    op.drop_column("trade_journal", "net_pnl")
    op.drop_column("trade_journal", "total_costs")
    op.drop_column("trade_journal", "gross_pnl")
