"""Persist the verified reproducibility status of strategy versions."""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004_strategy_version_reproducibility"
down_revision = "0003_strategy_registry_authority"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "strategy_versions",
        sa.Column("reproducibility_status", sa.String(32), nullable=False, server_default="NON_REPRODUCIBLE"),
    )
    op.create_check_constraint(
        "ck_strategy_versions_reproducibility_status",
        "strategy_versions",
        "reproducibility_status IN ('REPRODUCIBLE', 'NON_REPRODUCIBLE')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_strategy_versions_reproducibility_status", "strategy_versions", type_="check")
    op.drop_column("strategy_versions", "reproducibility_status")
