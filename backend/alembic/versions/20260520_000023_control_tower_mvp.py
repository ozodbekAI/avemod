"""Control Tower MVP persistence tables.

Revision ID: 20260520_000023
Revises: 20260519_000022
Create Date: 2026-05-20 10:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260520_000023"
down_revision = "20260519_000022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "action_recommendations",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("account_id", sa.BigInteger(), sa.ForeignKey("wb_accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sku_id", sa.BigInteger(), sa.ForeignKey("core_sku.id", ondelete="SET NULL"), nullable=True),
        sa.Column("nm_id", sa.BigInteger(), nullable=True),
        sa.Column("vendor_code", sa.String(length=255), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("action_type", sa.String(length=64), nullable=False),
        sa.Column("priority", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="new"),
        sa.Column("reason_code", sa.String(length=64), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("calculation_basis", sa.Text(), nullable=True),
        sa.Column("expected_effect_amount", sa.Numeric(18, 4), nullable=True),
        sa.Column("confidence", sa.String(length=16), nullable=False, server_default="medium"),
        sa.Column("trust_state", sa.String(length=32), nullable=False, server_default="data_blocked"),
        sa.Column("blocked_reasons", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("source_date_from", sa.Date(), nullable=True),
        sa.Column("source_date_to", sa.Date(), nullable=True),
        sa.Column("source_snapshot_hash", sa.String(length=128), nullable=True),
        sa.Column("action_unique_key", sa.String(length=255), nullable=False),
        sa.Column("assigned_to", sa.BigInteger(), sa.ForeignKey("auth_users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("user_comment", sa.Text(), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("action_unique_key", name="uq_action_recommendations_action_unique_key"),
    )
    op.create_index("ix_action_recommendations_account_id", "action_recommendations", ["account_id"])
    op.create_index("ix_action_recommendations_sku_id", "action_recommendations", ["sku_id"])
    op.create_index("ix_action_recommendations_nm_id", "action_recommendations", ["nm_id"])
    op.create_index("ix_action_recommendations_vendor_code", "action_recommendations", ["vendor_code"])
    op.create_index("ix_action_recommendations_action_type", "action_recommendations", ["action_type"])
    op.create_index("ix_action_recommendations_priority", "action_recommendations", ["priority"])
    op.create_index("ix_action_recommendations_status", "action_recommendations", ["status"])
    op.create_index("ix_action_recommendations_reason_code", "action_recommendations", ["reason_code"])
    op.create_index("ix_action_recommendations_action_unique_key", "action_recommendations", ["action_unique_key"])

    op.create_table(
        "action_recommendation_history",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("action_id", sa.BigInteger(), sa.ForeignKey("action_recommendations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("previous_status", sa.String(length=32), nullable=True),
        sa.Column("new_status", sa.String(length=32), nullable=False),
        sa.Column("changed_by_user_id", sa.BigInteger(), sa.ForeignKey("auth_users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_action_recommendation_history_action_id", "action_recommendation_history", ["action_id"])

    op.create_table(
        "alert_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("account_id", sa.BigInteger(), sa.ForeignKey("wb_accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("action_id", sa.BigInteger(), sa.ForeignKey("action_recommendations.id", ondelete="SET NULL"), nullable=True),
        sa.Column("alert_type", sa.String(length=64), nullable=False),
        sa.Column("severity", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="new"),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("confidence", sa.String(length=16), nullable=False, server_default="medium"),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("snoozed_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_alert_events_account_id", "alert_events", ["account_id"])
    op.create_index("ix_alert_events_action_id", "alert_events", ["action_id"])
    op.create_index("ix_alert_events_alert_type", "alert_events", ["alert_type"])
    op.create_index("ix_alert_events_severity", "alert_events", ["severity"])
    op.create_index("ix_alert_events_status", "alert_events", ["status"])

    op.create_table(
        "user_business_settings",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("account_id", sa.BigInteger(), sa.ForeignKey("wb_accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("updated_by_user_id", sa.BigInteger(), sa.ForeignKey("auth_users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("settings_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("account_id", name="uq_user_business_settings_account_id"),
    )
    op.create_index("ix_user_business_settings_account_id", "user_business_settings", ["account_id"])

    op.create_table(
        "user_business_settings_audit",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("account_id", sa.BigInteger(), sa.ForeignKey("wb_accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("changed_by_user_id", sa.BigInteger(), sa.ForeignKey("auth_users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("previous_settings_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("next_settings_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_user_business_settings_audit_account_id", "user_business_settings_audit", ["account_id"])

    op.create_table(
        "formula_audit_runs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("account_id", sa.BigInteger(), sa.ForeignKey("wb_accounts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("scope", sa.String(length=64), nullable=False, server_default="global"),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("result_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_formula_audit_runs_account_id", "formula_audit_runs", ["account_id"])
    op.create_index("ix_formula_audit_runs_status", "formula_audit_runs", ["status"])


def downgrade() -> None:
    raise NotImplementedError("Downgrades are intentionally not supported.")
