"""Add Dynamic Problem Engine evaluation run logs.

Revision ID: 20260706_000060
Revises: 20260706_000059
Create Date: 2026-07-06
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260706_000060"
down_revision = "20260706_000059"
branch_labels = None
depends_on = None


JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        "problem_evaluation_run_logs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("account_id", sa.BigInteger(), nullable=True),
        sa.Column("trigger", sa.String(length=64), nullable=False),
        sa.Column("scope", sa.String(length=64), nullable=False),
        sa.Column("sync_run_id", sa.BigInteger(), nullable=True),
        sa.Column("problem_instance_id", sa.BigInteger(), nullable=True),
        sa.Column("actor_user_id", sa.BigInteger(), nullable=True),
        sa.Column("nm_ids_json", JSONB, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("rules_evaluated", sa.Integer(), nullable=False),
        sa.Column("entities_evaluated", sa.Integer(), nullable=False),
        sa.Column("issues_created", sa.Integer(), nullable=False),
        sa.Column("issues_updated", sa.Integer(), nullable=False),
        sa.Column("issues_resolved", sa.Integer(), nullable=False),
        sa.Column("issues_candidate_resolved", sa.Integer(), nullable=False),
        sa.Column("issues_skipped", sa.Integer(), nullable=False),
        sa.Column("errors_json", JSONB, nullable=False),
        sa.Column("warnings_json", JSONB, nullable=False),
        sa.Column("result_json", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["wb_accounts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["sync_run_id"], ["wb_sync_runs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["problem_instance_id"], ["problem_instances.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["auth_users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_problem_evaluation_run_logs_account_id", "problem_evaluation_run_logs", ["account_id"])
    op.create_index(
        "ix_problem_evaluation_run_logs_account_started",
        "problem_evaluation_run_logs",
        ["account_id", "started_at"],
    )
    op.create_index("ix_problem_evaluation_run_logs_sync_run_id", "problem_evaluation_run_logs", ["sync_run_id"])
    op.create_index(
        "ix_problem_evaluation_run_logs_problem_instance_id",
        "problem_evaluation_run_logs",
        ["problem_instance_id"],
    )
    op.create_index("ix_problem_evaluation_run_logs_actor_user_id", "problem_evaluation_run_logs", ["actor_user_id"])
    op.create_index("ix_problem_evaluation_run_logs_trigger", "problem_evaluation_run_logs", ["trigger"])
    op.create_index("ix_problem_evaluation_run_logs_status", "problem_evaluation_run_logs", ["status"])


def downgrade() -> None:
    op.drop_index("ix_problem_evaluation_run_logs_status", table_name="problem_evaluation_run_logs")
    op.drop_index("ix_problem_evaluation_run_logs_trigger", table_name="problem_evaluation_run_logs")
    op.drop_index("ix_problem_evaluation_run_logs_actor_user_id", table_name="problem_evaluation_run_logs")
    op.drop_index("ix_problem_evaluation_run_logs_problem_instance_id", table_name="problem_evaluation_run_logs")
    op.drop_index("ix_problem_evaluation_run_logs_sync_run_id", table_name="problem_evaluation_run_logs")
    op.drop_index("ix_problem_evaluation_run_logs_account_started", table_name="problem_evaluation_run_logs")
    op.drop_index("ix_problem_evaluation_run_logs_account_id", table_name="problem_evaluation_run_logs")
    op.drop_table("problem_evaluation_run_logs")
