"""Move mutable strategy registry governance to SQLAlchemy."""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003_strategy_registry_authority"
down_revision = "0002_strategy_governance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("strategies", sa.Column("registry_version", sa.String(80), nullable=False, server_default="1.0.0"))
    op.add_column("strategies", sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("strategies", sa.Column("rollout_pct", sa.Integer(), nullable=False, server_default="100"))
    op.add_column("strategies", sa.Column("supported_regimes_json", sa.Text(), nullable=False, server_default='["Any"]'))
    op.add_column("strategies", sa.Column("owner", sa.String(120), nullable=False, server_default="quantgrid"))
    op.add_column("strategies", sa.Column("notes", sa.Text(), nullable=False, server_default=""))
    op.add_column("strategies", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.create_index("ix_strategies_enabled", "strategies", ["enabled"])
    op.create_table(
        "strategy_governance_audit",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("strategy_id", sa.String(36), sa.ForeignKey("strategies.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("event", sa.String(80), nullable=False),
        sa.Column("details_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_strategy_governance_audit_strategy_id", "strategy_governance_audit", ["strategy_id"])
    op.create_index("ix_strategy_governance_audit_created_at", "strategy_governance_audit", ["created_at"])


def downgrade() -> None:
    op.drop_table("strategy_governance_audit")
    op.drop_index("ix_strategies_enabled", table_name="strategies")
    for column in ("updated_at", "notes", "owner", "supported_regimes_json", "rollout_pct", "enabled", "registry_version"):
        op.drop_column("strategies", column)
