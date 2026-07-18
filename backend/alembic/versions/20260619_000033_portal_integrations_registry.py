"""Add DB-backed portal integration registry.

Revision ID: 20260619_000033
Revises: 20260615_000032
Create Date: 2026-06-19 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260619_000033"
down_revision = "20260615_000032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "portal_integrations",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("account_id", sa.BigInteger(), nullable=False),
        sa.Column("module", sa.String(length=64), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("mode", sa.String(length=32), nullable=False, server_default="local"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="not_configured"),
        sa.Column("configuration_encrypted_json", sa.Text(), nullable=True),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(length=128), nullable=True),
        sa.Column("last_error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["wb_accounts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("account_id", "module", name="uq_portal_integrations_account_module"),
    )
    op.create_index("ix_portal_integrations_account_id", "portal_integrations", ["account_id"])
    op.create_index("ix_portal_integrations_account_module", "portal_integrations", ["account_id", "module"])
    op.create_index("ix_portal_integrations_enabled", "portal_integrations", ["enabled"])
    op.create_index("ix_portal_integrations_last_success_at", "portal_integrations", ["last_success_at"])
    op.create_index("ix_portal_integrations_last_sync_at", "portal_integrations", ["last_sync_at"])
    op.create_index("ix_portal_integrations_mode", "portal_integrations", ["mode"])
    op.create_index("ix_portal_integrations_module", "portal_integrations", ["module"])
    op.create_index("ix_portal_integrations_status", "portal_integrations", ["status"])

    op.create_table(
        "portal_module_sync_runs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("account_id", sa.BigInteger(), nullable=False),
        sa.Column("module", sa.String(length=64), nullable=False),
        sa.Column("run_type", sa.String(length=64), nullable=False, server_default="sync"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="queued"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rows_received", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rows_created", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rows_updated", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rows_failed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["wb_accounts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_portal_module_sync_runs_account_id", "portal_module_sync_runs", ["account_id"])
    op.create_index(
        "ix_portal_module_sync_runs_account_module_started",
        "portal_module_sync_runs",
        ["account_id", "module", sa.text("started_at DESC")],
    )
    op.create_index("ix_portal_module_sync_runs_finished_at", "portal_module_sync_runs", ["finished_at"])
    op.create_index("ix_portal_module_sync_runs_module", "portal_module_sync_runs", ["module"])
    op.create_index("ix_portal_module_sync_runs_run_type", "portal_module_sync_runs", ["run_type"])
    op.create_index("ix_portal_module_sync_runs_started_at", "portal_module_sync_runs", ["started_at"])
    op.create_index("ix_portal_module_sync_runs_status", "portal_module_sync_runs", ["status"])


def downgrade() -> None:
    op.drop_index("ix_portal_module_sync_runs_status", table_name="portal_module_sync_runs")
    op.drop_index("ix_portal_module_sync_runs_started_at", table_name="portal_module_sync_runs")
    op.drop_index("ix_portal_module_sync_runs_run_type", table_name="portal_module_sync_runs")
    op.drop_index("ix_portal_module_sync_runs_module", table_name="portal_module_sync_runs")
    op.drop_index("ix_portal_module_sync_runs_finished_at", table_name="portal_module_sync_runs")
    op.drop_index("ix_portal_module_sync_runs_account_module_started", table_name="portal_module_sync_runs")
    op.drop_index("ix_portal_module_sync_runs_account_id", table_name="portal_module_sync_runs")
    op.drop_table("portal_module_sync_runs")

    op.drop_index("ix_portal_integrations_status", table_name="portal_integrations")
    op.drop_index("ix_portal_integrations_module", table_name="portal_integrations")
    op.drop_index("ix_portal_integrations_mode", table_name="portal_integrations")
    op.drop_index("ix_portal_integrations_last_sync_at", table_name="portal_integrations")
    op.drop_index("ix_portal_integrations_last_success_at", table_name="portal_integrations")
    op.drop_index("ix_portal_integrations_enabled", table_name="portal_integrations")
    op.drop_index("ix_portal_integrations_account_module", table_name="portal_integrations")
    op.drop_index("ix_portal_integrations_account_id", table_name="portal_integrations")
    op.drop_table("portal_integrations")
