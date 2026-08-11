"""Immutable strategy and parameter provenance entities."""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002_strategy_governance"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("strategies",
        sa.Column("id", sa.String(36), primary_key=True), sa.Column("name", sa.String(120), nullable=False),
        sa.Column("display_name", sa.String(200)), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("name", name="uq_strategies_name"))
    op.create_index("ix_strategies_name", "strategies", ["name"])
    op.create_table("parameter_snapshots",
        sa.Column("id", sa.String(36), primary_key=True), sa.Column("canonical_parameters", sa.Text(), nullable=False),
        sa.Column("parameter_hash", sa.String(64), nullable=False), sa.Column("schema_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("parameter_hash", name="uq_parameter_snapshots_hash"))
    op.create_index("ix_parameter_snapshots_parameter_hash", "parameter_snapshots", ["parameter_hash"])
    op.create_index("ix_parameter_snapshots_schema_hash", "parameter_snapshots", ["schema_hash"])
    op.create_table("strategy_versions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("strategy_id", sa.String(36), sa.ForeignKey("strategies.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("version_string", sa.String(80), nullable=False), sa.Column("git_commit_sha", sa.String(40), nullable=False),
        sa.Column("git_tree_hash", sa.String(64), nullable=False), sa.Column("git_is_clean", sa.Boolean(), nullable=False),
        sa.Column("code_snapshot_hash", sa.String(64), nullable=False), sa.Column("dependency_lock_hash", sa.String(64), nullable=False),
        sa.Column("execution_environment_hash", sa.String(64), nullable=False), sa.Column("parameter_schema_hash", sa.String(64), nullable=False),
        sa.Column("parameter_snapshot_id", sa.String(36), sa.ForeignKey("parameter_snapshots.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("created_by", sa.String(120), nullable=False),
        sa.Column("governance_state", sa.String(40), nullable=False, server_default="DRAFT"),
        sa.UniqueConstraint("strategy_id", "version_string", name="uq_strategy_version_name"))
    op.create_index("ix_strategy_versions_strategy_id", "strategy_versions", ["strategy_id"])
    op.create_index("ix_strategy_versions_parameter_snapshot_id", "strategy_versions", ["parameter_snapshot_id"])
    op.create_index("ix_strategy_versions_governance_state", "strategy_versions", ["governance_state"])
    if op.get_bind().dialect.name == "postgresql":
        op.execute("""
            CREATE FUNCTION prevent_governance_provenance_mutation() RETURNS trigger AS $$
            BEGIN
                IF ROW(NEW.strategy_id, NEW.version_string, NEW.git_commit_sha, NEW.git_tree_hash,
                       NEW.git_is_clean, NEW.code_snapshot_hash, NEW.dependency_lock_hash,
                       NEW.execution_environment_hash, NEW.parameter_schema_hash,
                       NEW.parameter_snapshot_id, NEW.created_at, NEW.created_by)
                   IS DISTINCT FROM
                   ROW(OLD.strategy_id, OLD.version_string, OLD.git_commit_sha, OLD.git_tree_hash,
                       OLD.git_is_clean, OLD.code_snapshot_hash, OLD.dependency_lock_hash,
                       OLD.execution_environment_hash, OLD.parameter_schema_hash,
                       OLD.parameter_snapshot_id, OLD.created_at, OLD.created_by) THEN
                    RAISE EXCEPTION 'StrategyVersion provenance is immutable';
                END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
            CREATE TRIGGER strategy_versions_immutable_provenance
            BEFORE UPDATE ON strategy_versions FOR EACH ROW
            EXECUTE FUNCTION prevent_governance_provenance_mutation();
            CREATE FUNCTION prevent_parameter_snapshot_mutation() RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION 'ParameterSnapshot is immutable';
            END;
            $$ LANGUAGE plpgsql;
            CREATE TRIGGER parameter_snapshots_immutable
            BEFORE UPDATE ON parameter_snapshots FOR EACH ROW
            EXECUTE FUNCTION prevent_parameter_snapshot_mutation();
        """)


def downgrade() -> None:
    op.drop_table("strategy_versions")
    op.drop_table("parameter_snapshots")
    op.drop_index("ix_strategies_name", table_name="strategies")
    op.drop_table("strategies")
