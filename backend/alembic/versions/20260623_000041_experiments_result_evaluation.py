"""Add local experiments result evaluation tables.

Revision ID: 20260623_000041
Revises: 20260623_000040
Create Date: 2026-06-23 12:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260623_000041"
down_revision = "20260623_000040"
branch_labels = None
depends_on = None

JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        "experiments",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("account_id", sa.BigInteger(), nullable=False),
        sa.Column("nm_id", sa.BigInteger(), nullable=True),
        sa.Column("sku_id", sa.BigInteger(), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("experiment_type", sa.String(length=32), nullable=False),
        sa.Column("intervention_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("hypothesis", sa.Text(), nullable=False),
        sa.Column("primary_metric", sa.String(length=64), nullable=False),
        sa.Column("secondary_metrics_json", JSONB, nullable=False),
        sa.Column("guardrail_metrics_json", JSONB, nullable=False),
        sa.Column("baseline_days", sa.Integer(), nullable=False),
        sa.Column("post_days", sa.Integer(), nullable=False),
        sa.Column("evaluation_delay_days", sa.Integer(), nullable=False),
        sa.Column("planned_start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("intervention_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("evaluation_due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", sa.BigInteger(), nullable=True),
        sa.Column("source_module", sa.String(length=64), nullable=True),
        sa.Column("source_action_key", sa.String(length=255), nullable=True),
        sa.Column("source_project_id", sa.String(length=255), nullable=True),
        sa.Column("is_test", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")),
        sa.Column("baseline_summary_json", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("progress_json", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("warnings_json", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.ForeignKeyConstraint(["account_id"], ["wb_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["auth_users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["sku_id"], ["core_sku.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("account_id", "source_module", "source_action_key", name="uq_experiments_source_action"),
    )
    op.create_index("ix_experiments_account_id", "experiments", ["account_id"])
    op.create_index("ix_experiments_account_nm_status", "experiments", ["account_id", "nm_id", "status"])
    op.create_index("ix_experiments_nm_id", "experiments", ["nm_id"])
    op.create_index("ix_experiments_sku_id", "experiments", ["sku_id"])
    op.create_index("ix_experiments_status", "experiments", ["status"])
    op.create_index("ix_experiments_intervention_type", "experiments", ["intervention_type"])
    op.create_index("ix_experiments_started_at", "experiments", ["started_at"])
    op.create_index("ix_experiments_intervention_at", "experiments", ["intervention_at"])
    op.create_index("ix_experiments_evaluation_due_at", "experiments", ["evaluation_due_at"])

    op.create_table(
        "experiment_interventions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("account_id", sa.BigInteger(), nullable=False),
        sa.Column("experiment_id", sa.BigInteger(), nullable=False),
        sa.Column("intervention_type", sa.String(length=32), nullable=False),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("applied_by_user_id", sa.BigInteger(), nullable=True),
        sa.Column("application_mode", sa.String(length=32), nullable=False),
        sa.Column("before_reference_json", JSONB, nullable=False),
        sa.Column("after_reference_json", JSONB, nullable=False),
        sa.Column("change_summary", sa.Text(), nullable=False),
        sa.Column("external_reference", sa.String(length=255), nullable=True),
        sa.Column("confirmed_by_sync", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["account_id"], ["wb_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["applied_by_user_id"], ["auth_users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["experiment_id"], ["experiments.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_experiment_interventions_account_id", "experiment_interventions", ["account_id"])
    op.create_index("ix_experiment_interventions_experiment_id", "experiment_interventions", ["experiment_id"])
    op.create_index("ix_experiment_interventions_applied_at", "experiment_interventions", ["applied_at"])

    op.create_table(
        "experiment_metric_snapshots",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("account_id", sa.BigInteger(), nullable=False),
        sa.Column("experiment_id", sa.BigInteger(), nullable=False),
        sa.Column("window_type", sa.String(length=32), nullable=False),
        sa.Column("metric_date", sa.Date(), nullable=False),
        sa.Column("metric_name", sa.String(length=64), nullable=False),
        sa.Column("metric_value", sa.Numeric(18, 4), nullable=True),
        sa.Column("metric_unit", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("data_status", sa.String(length=32), nullable=False),
        sa.Column("data_freshness_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_complete", sa.Boolean(), nullable=False),
        sa.Column("warnings_json", JSONB, nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["wb_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["experiment_id"], ["experiments.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("experiment_id", "window_type", "metric_date", "metric_name", name="uq_experiment_metric_snapshot_day"),
    )
    op.create_index("ix_experiment_metric_snapshots_account_id", "experiment_metric_snapshots", ["account_id"])
    op.create_index("ix_experiment_metric_snapshots_experiment_id", "experiment_metric_snapshots", ["experiment_id"])
    op.create_index("ix_experiment_metric_snapshots_metric_date", "experiment_metric_snapshots", ["metric_date"])
    op.create_index("ix_experiment_metric_snapshots_metric_name", "experiment_metric_snapshots", ["metric_name"])

    op.create_table(
        "experiment_evaluations",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("account_id", sa.BigInteger(), nullable=False),
        sa.Column("experiment_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("evaluation_version", sa.String(length=32), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("baseline_window_json", JSONB, nullable=False),
        sa.Column("post_window_json", JSONB, nullable=False),
        sa.Column("primary_result_json", JSONB, nullable=False),
        sa.Column("secondary_results_json", JSONB, nullable=False),
        sa.Column("guardrail_results_json", JSONB, nullable=False),
        sa.Column("data_sufficiency_json", JSONB, nullable=False),
        sa.Column("confounders_json", JSONB, nullable=False),
        sa.Column("confidence", sa.String(length=16), nullable=False),
        sa.Column("outcome", sa.String(length=32), nullable=False),
        sa.Column("seller_summary", sa.Text(), nullable=False),
        sa.Column("technical_summary_json", JSONB, nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["wb_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["experiment_id"], ["experiments.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_experiment_evaluations_account_id", "experiment_evaluations", ["account_id"])
    op.create_index("ix_experiment_evaluations_experiment_id", "experiment_evaluations", ["experiment_id"])
    op.create_index("ix_experiment_evaluations_outcome", "experiment_evaluations", ["outcome"])
    op.create_index("ix_experiment_evaluations_evaluated_at", "experiment_evaluations", ["evaluated_at"])

    op.create_table(
        "experiment_settings",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("account_id", sa.BigInteger(), nullable=False),
        sa.Column("default_baseline_days", sa.Integer(), nullable=False),
        sa.Column("default_post_days", sa.Integer(), nullable=False),
        sa.Column("default_evaluation_delay_days", sa.Integer(), nullable=False),
        sa.Column("minimum_orders", sa.Integer(), nullable=False),
        sa.Column("minimum_revenue", sa.Numeric(18, 4), nullable=False),
        sa.Column("minimum_views", sa.Integer(), nullable=True),
        sa.Column("maximum_stockout_days", sa.Integer(), nullable=False),
        sa.Column("allow_overlapping_experiments", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")),
        sa.Column("weekday_matched_baseline", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")),
        sa.ForeignKeyConstraint(["account_id"], ["wb_accounts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("account_id", name="uq_experiment_settings_account"),
    )
    op.create_index("ix_experiment_settings_account_id", "experiment_settings", ["account_id"])


def downgrade() -> None:
    op.drop_table("experiment_settings")
    op.drop_table("experiment_evaluations")
    op.drop_table("experiment_metric_snapshots")
    op.drop_table("experiment_interventions")
    op.drop_table("experiments")
