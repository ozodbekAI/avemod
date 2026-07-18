"""Add Dynamic Problem Definition Engine tables.

Revision ID: 20260706_000056
Revises: 20260701_000055
Create Date: 2026-07-06
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260706_000056"
down_revision = "20260701_000055"
branch_labels = None
depends_on = None


JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        "metric_catalog",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("metric_code", sa.String(length=128), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        sa.Column("value_type", sa.String(length=32), nullable=False),
        sa.Column("unit", sa.String(length=64), nullable=True),
        sa.Column("grain", sa.String(length=64), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("source_module", sa.String(length=64), nullable=False),
        sa.Column("formula_json", JSONB, nullable=True),
        sa.Column("source_tables_json", JSONB, server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("source_endpoints_json", JSONB, server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("required_metrics_json", JSONB, server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("trust_state", sa.String(length=32), server_default="provisional", nullable=False),
        sa.Column("is_admin_visible", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("is_deprecated", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("metric_code", name="uq_metric_catalog_metric_code"),
    )
    op.create_index("ix_metric_catalog_metric_code", "metric_catalog", ["metric_code"])
    op.create_index("ix_metric_catalog_source_module", "metric_catalog", ["source_module"])
    op.create_index("ix_metric_catalog_trust_state", "metric_catalog", ["trust_state"])
    op.create_index("ix_metric_catalog_is_admin_visible", "metric_catalog", ["is_admin_visible"])
    op.create_index("ix_metric_catalog_is_deprecated", "metric_catalog", ["is_deprecated"])

    op.create_table(
        "problem_definitions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("problem_code", sa.String(length=128), nullable=False),
        sa.Column("source_module", sa.String(length=64), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("title_template", sa.Text(), nullable=False),
        sa.Column("description_template", sa.Text(), nullable=False),
        sa.Column("recommendation_template", sa.Text(), nullable=False),
        sa.Column("impact_type_default", sa.String(length=64), nullable=False),
        sa.Column("trust_state_default", sa.String(length=32), server_default="provisional", nullable=False),
        sa.Column("severity_default", sa.String(length=32), server_default="medium", nullable=False),
        sa.Column("allowed_actions_json", JSONB, server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="draft", nullable=False),
        sa.Column("created_by_user_id", sa.BigInteger(), nullable=True),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["auth_users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("problem_code", name="uq_problem_definitions_problem_code"),
    )
    op.create_index("ix_problem_definitions_problem_code", "problem_definitions", ["problem_code"])
    op.create_index("ix_problem_definitions_source_module", "problem_definitions", ["source_module"])
    op.create_index("ix_problem_definitions_category", "problem_definitions", ["category"])
    op.create_index("ix_problem_definitions_entity_type", "problem_definitions", ["entity_type"])
    op.create_index("ix_problem_definitions_impact_type_default", "problem_definitions", ["impact_type_default"])
    op.create_index("ix_problem_definitions_trust_state_default", "problem_definitions", ["trust_state_default"])
    op.create_index("ix_problem_definitions_severity_default", "problem_definitions", ["severity_default"])
    op.create_index("ix_problem_definitions_status", "problem_definitions", ["status"])
    op.create_index("ix_problem_definitions_created_by_user_id", "problem_definitions", ["created_by_user_id"])

    op.create_table(
        "problem_rule_versions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("problem_definition_id", sa.BigInteger(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="draft", nullable=False),
        sa.Column("evaluation_grain", sa.String(length=64), nullable=False),
        sa.Column("lookback_days", sa.Integer(), server_default="30", nullable=False),
        sa.Column("condition_json", JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("impact_formula_json", JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("severity_formula_json", JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("confidence_formula_json", JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("dedup_key_template", sa.String(length=512), nullable=False),
        sa.Column("recheck_rule_json", JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("evidence_template_json", JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("created_by_user_id", sa.BigInteger(), nullable=True),
        sa.Column("published_by_user_id", sa.BigInteger(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["auth_users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["problem_definition_id"], ["problem_definitions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["published_by_user_id"], ["auth_users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("problem_definition_id", "version", name="uq_problem_rule_versions_definition_version"),
    )
    op.create_index(
        "ix_problem_rule_versions_definition_version",
        "problem_rule_versions",
        ["problem_definition_id", "version"],
    )
    op.create_index("ix_problem_rule_versions_problem_definition_id", "problem_rule_versions", ["problem_definition_id"])
    op.create_index("ix_problem_rule_versions_status", "problem_rule_versions", ["status"])
    op.create_index("ix_problem_rule_versions_created_by_user_id", "problem_rule_versions", ["created_by_user_id"])
    op.create_index("ix_problem_rule_versions_published_by_user_id", "problem_rule_versions", ["published_by_user_id"])
    op.create_index("ix_problem_rule_versions_published_at", "problem_rule_versions", ["published_at"])

    op.create_table(
        "problem_instances",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("account_id", sa.BigInteger(), nullable=False),
        sa.Column("problem_code", sa.String(length=128), nullable=False),
        sa.Column("problem_definition_id", sa.BigInteger(), nullable=False),
        sa.Column("rule_version_id", sa.BigInteger(), nullable=False),
        sa.Column("source_module", sa.String(length=64), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.String(length=255), nullable=False),
        sa.Column("nm_id", sa.BigInteger(), nullable=True),
        sa.Column("vendor_code", sa.String(length=255), nullable=True),
        sa.Column("dedup_key", sa.String(length=255), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("recommendation", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="new", nullable=False),
        sa.Column("impact_type", sa.String(length=64), nullable=False),
        sa.Column("money_impact_amount", sa.Numeric(18, 4), nullable=True),
        sa.Column("money_impact_currency", sa.String(length=8), nullable=True),
        sa.Column("trust_state", sa.String(length=32), nullable=False),
        sa.Column("confidence", sa.String(length=32), nullable=True),
        sa.Column("evidence_ledger_json", JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("calculation_snapshot_json", JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dismissed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dismiss_reason", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["account_id"], ["wb_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["problem_definition_id"], ["problem_definitions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["rule_version_id"], ["problem_rule_versions.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "account_id",
            "problem_code",
            "entity_type",
            "entity_id",
            "dedup_key",
            name="uq_problem_instances_account_problem_entity_dedup",
        ),
    )
    op.create_index("ix_problem_instances_account_status", "problem_instances", ["account_id", "status"])
    op.create_index("ix_problem_instances_account_problem_code", "problem_instances", ["account_id", "problem_code"])
    op.create_index("ix_problem_instances_dedup_key", "problem_instances", ["dedup_key"])
    op.create_index("ix_problem_instances_account_id", "problem_instances", ["account_id"])
    op.create_index("ix_problem_instances_problem_code", "problem_instances", ["problem_code"])
    op.create_index("ix_problem_instances_problem_definition_id", "problem_instances", ["problem_definition_id"])
    op.create_index("ix_problem_instances_rule_version_id", "problem_instances", ["rule_version_id"])
    op.create_index("ix_problem_instances_source_module", "problem_instances", ["source_module"])
    op.create_index("ix_problem_instances_entity_type", "problem_instances", ["entity_type"])
    op.create_index("ix_problem_instances_entity_id", "problem_instances", ["entity_id"])
    op.create_index("ix_problem_instances_nm_id", "problem_instances", ["nm_id"])
    op.create_index("ix_problem_instances_vendor_code", "problem_instances", ["vendor_code"])
    op.create_index("ix_problem_instances_severity", "problem_instances", ["severity"])
    op.create_index("ix_problem_instances_status", "problem_instances", ["status"])
    op.create_index("ix_problem_instances_impact_type", "problem_instances", ["impact_type"])
    op.create_index("ix_problem_instances_trust_state", "problem_instances", ["trust_state"])
    op.create_index("ix_problem_instances_resolved_at", "problem_instances", ["resolved_at"])
    op.create_index("ix_problem_instances_dismissed_at", "problem_instances", ["dismissed_at"])

    op.create_table(
        "problem_instance_history",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("problem_instance_id", sa.BigInteger(), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("old_value_json", JSONB, nullable=True),
        sa.Column("new_value_json", JSONB, nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("actor_user_id", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["actor_user_id"], ["auth_users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["problem_instance_id"], ["problem_instances.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_problem_instance_history_problem_instance_id", "problem_instance_history", ["problem_instance_id"])
    op.create_index("ix_problem_instance_history_event_type", "problem_instance_history", ["event_type"])
    op.create_index("ix_problem_instance_history_actor_user_id", "problem_instance_history", ["actor_user_id"])

    op.create_table(
        "admin_rule_test_runs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("rule_version_id", sa.BigInteger(), nullable=False),
        sa.Column("account_id", sa.BigInteger(), nullable=True),
        sa.Column("date_from", sa.Date(), nullable=False),
        sa.Column("date_to", sa.Date(), nullable=False),
        sa.Column("matched_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("sample_issues_json", JSONB, server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("total_impact_amount", sa.Numeric(18, 4), nullable=True),
        sa.Column("warnings_json", JSONB, server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("created_by_user_id", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["wb_accounts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["auth_users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["rule_version_id"], ["problem_rule_versions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_admin_rule_test_runs_rule_version_id", "admin_rule_test_runs", ["rule_version_id"])
    op.create_index("ix_admin_rule_test_runs_account_id", "admin_rule_test_runs", ["account_id"])
    op.create_index("ix_admin_rule_test_runs_created_by_user_id", "admin_rule_test_runs", ["created_by_user_id"])


def downgrade() -> None:
    op.drop_index("ix_admin_rule_test_runs_created_by_user_id", table_name="admin_rule_test_runs")
    op.drop_index("ix_admin_rule_test_runs_account_id", table_name="admin_rule_test_runs")
    op.drop_index("ix_admin_rule_test_runs_rule_version_id", table_name="admin_rule_test_runs")
    op.drop_table("admin_rule_test_runs")

    op.drop_index("ix_problem_instance_history_actor_user_id", table_name="problem_instance_history")
    op.drop_index("ix_problem_instance_history_event_type", table_name="problem_instance_history")
    op.drop_index("ix_problem_instance_history_problem_instance_id", table_name="problem_instance_history")
    op.drop_table("problem_instance_history")

    op.drop_index("ix_problem_instances_dismissed_at", table_name="problem_instances")
    op.drop_index("ix_problem_instances_resolved_at", table_name="problem_instances")
    op.drop_index("ix_problem_instances_trust_state", table_name="problem_instances")
    op.drop_index("ix_problem_instances_impact_type", table_name="problem_instances")
    op.drop_index("ix_problem_instances_status", table_name="problem_instances")
    op.drop_index("ix_problem_instances_severity", table_name="problem_instances")
    op.drop_index("ix_problem_instances_vendor_code", table_name="problem_instances")
    op.drop_index("ix_problem_instances_nm_id", table_name="problem_instances")
    op.drop_index("ix_problem_instances_entity_id", table_name="problem_instances")
    op.drop_index("ix_problem_instances_entity_type", table_name="problem_instances")
    op.drop_index("ix_problem_instances_source_module", table_name="problem_instances")
    op.drop_index("ix_problem_instances_rule_version_id", table_name="problem_instances")
    op.drop_index("ix_problem_instances_problem_definition_id", table_name="problem_instances")
    op.drop_index("ix_problem_instances_problem_code", table_name="problem_instances")
    op.drop_index("ix_problem_instances_account_id", table_name="problem_instances")
    op.drop_index("ix_problem_instances_dedup_key", table_name="problem_instances")
    op.drop_index("ix_problem_instances_account_problem_code", table_name="problem_instances")
    op.drop_index("ix_problem_instances_account_status", table_name="problem_instances")
    op.drop_table("problem_instances")

    op.drop_index("ix_problem_rule_versions_published_at", table_name="problem_rule_versions")
    op.drop_index("ix_problem_rule_versions_published_by_user_id", table_name="problem_rule_versions")
    op.drop_index("ix_problem_rule_versions_created_by_user_id", table_name="problem_rule_versions")
    op.drop_index("ix_problem_rule_versions_status", table_name="problem_rule_versions")
    op.drop_index("ix_problem_rule_versions_problem_definition_id", table_name="problem_rule_versions")
    op.drop_index("ix_problem_rule_versions_definition_version", table_name="problem_rule_versions")
    op.drop_table("problem_rule_versions")

    op.drop_index("ix_problem_definitions_created_by_user_id", table_name="problem_definitions")
    op.drop_index("ix_problem_definitions_status", table_name="problem_definitions")
    op.drop_index("ix_problem_definitions_severity_default", table_name="problem_definitions")
    op.drop_index("ix_problem_definitions_trust_state_default", table_name="problem_definitions")
    op.drop_index("ix_problem_definitions_impact_type_default", table_name="problem_definitions")
    op.drop_index("ix_problem_definitions_entity_type", table_name="problem_definitions")
    op.drop_index("ix_problem_definitions_category", table_name="problem_definitions")
    op.drop_index("ix_problem_definitions_source_module", table_name="problem_definitions")
    op.drop_index("ix_problem_definitions_problem_code", table_name="problem_definitions")
    op.drop_table("problem_definitions")

    op.drop_index("ix_metric_catalog_is_deprecated", table_name="metric_catalog")
    op.drop_index("ix_metric_catalog_is_admin_visible", table_name="metric_catalog")
    op.drop_index("ix_metric_catalog_trust_state", table_name="metric_catalog")
    op.drop_index("ix_metric_catalog_source_module", table_name="metric_catalog")
    op.drop_index("ix_metric_catalog_metric_code", table_name="metric_catalog")
    op.drop_table("metric_catalog")
