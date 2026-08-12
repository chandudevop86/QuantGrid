"""Add provenance to investment research records.

Existing research rows are marked legacy and are intentionally excluded from
production reads because older versions could persist synthetic demo data.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006_investment_research_source"
down_revision = "0005_dataset_snapshots"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "investment_research_scores",
        sa.Column("source", sa.String(40), nullable=False, server_default="legacy"),
    )
    op.create_index(
        "ix_investment_research_scores_source",
        "investment_research_scores",
        ["source"],
    )


def downgrade() -> None:
    op.drop_index("ix_investment_research_scores_source", table_name="investment_research_scores")
    op.drop_column("investment_research_scores", "source")
