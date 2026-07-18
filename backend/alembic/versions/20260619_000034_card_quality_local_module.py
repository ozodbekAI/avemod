"""Add local card quality module tables.

Revision ID: 20260619_000034
Revises: 20260619_000033
Create Date: 2026-06-19 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260619_000034"
down_revision = "20260619_000033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "card_quality_analysis_runs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("account_id", sa.BigInteger(), nullable=False),
        sa.Column("run_type", sa.String(length=64), server_default="single_product", nullable=False),
        sa.Column("status", sa.String(length=32), server_default="queued", nullable=False),
        sa.Column("requested_by_user_id", sa.BigInteger(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cards_total", sa.Integer(), server_default="0", nullable=False),
        sa.Column("cards_analyzed", sa.Integer(), server_default="0", nullable=False),
        sa.Column("cards_clean", sa.Integer(), server_default="0", nullable=False),
        sa.Column("cards_with_issues", sa.Integer(), server_default="0", nullable=False),
        sa.Column("issues_created", sa.Integer(), server_default="0", nullable=False),
        sa.Column("issues_resolved", sa.Integer(), server_default="0", nullable=False),
        sa.Column("source_revision", sa.String(length=128), nullable=True),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["wb_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["auth_users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_card_quality_analysis_runs_account_id", "card_quality_analysis_runs", ["account_id"])
    op.create_index("ix_card_quality_analysis_runs_account_started", "card_quality_analysis_runs", ["account_id", "started_at"])
    op.create_index("ix_card_quality_analysis_runs_account_status", "card_quality_analysis_runs", ["account_id", "status"])
    op.create_index("ix_card_quality_analysis_runs_requested_by_user_id", "card_quality_analysis_runs", ["requested_by_user_id"])
    op.create_index("ix_card_quality_analysis_runs_run_type", "card_quality_analysis_runs", ["run_type"])
    op.create_index("ix_card_quality_analysis_runs_started_at", "card_quality_analysis_runs", ["started_at"])
    op.create_index("ix_card_quality_analysis_runs_finished_at", "card_quality_analysis_runs", ["finished_at"])
    op.create_index("ix_card_quality_analysis_runs_status", "card_quality_analysis_runs", ["status"])

    op.create_table(
        "card_quality_snapshots",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("account_id", sa.BigInteger(), nullable=False),
        sa.Column("nm_id", sa.BigInteger(), nullable=False),
        sa.Column("source_card_id", sa.BigInteger(), nullable=True),
        sa.Column("source_revision", sa.String(length=128), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("brand", sa.String(length=255), nullable=True),
        sa.Column("subject_name", sa.String(length=255), nullable=True),
        sa.Column("vendor_code", sa.String(length=255), nullable=True),
        sa.Column("characteristics_json", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False),
        sa.Column("media_json", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("photos_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("video_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("source_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("analyzed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("score", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=32), server_default="not_analyzed", nullable=False),
        sa.Column("summary_json", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["wb_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_card_id"], ["wb_product_cards.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_card_quality_snapshots_account_id", "card_quality_snapshots", ["account_id"])
    op.create_index("ix_card_quality_snapshots_account_nm", "card_quality_snapshots", ["account_id", "nm_id"])
    op.create_index("ix_card_quality_snapshots_account_status", "card_quality_snapshots", ["account_id", "status"])
    op.create_index("ix_card_quality_snapshots_analyzed_at", "card_quality_snapshots", ["analyzed_at"])
    op.create_index("ix_card_quality_snapshots_nm_id", "card_quality_snapshots", ["nm_id"])
    op.create_index("ix_card_quality_snapshots_source_card_id", "card_quality_snapshots", ["source_card_id"])
    op.create_index("ix_card_quality_snapshots_source_revision", "card_quality_snapshots", ["source_revision"])
    op.create_index("ix_card_quality_snapshots_status", "card_quality_snapshots", ["status"])
    op.create_index("ix_card_quality_snapshots_vendor_code", "card_quality_snapshots", ["vendor_code"])

    op.create_table(
        "card_quality_issues",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("account_id", sa.BigInteger(), nullable=False),
        sa.Column("nm_id", sa.BigInteger(), nullable=False),
        sa.Column("snapshot_id", sa.BigInteger(), nullable=True),
        sa.Column("issue_code", sa.String(length=128), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("severity", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("business_explanation", sa.Text(), nullable=True),
        sa.Column("recommended_fix", sa.Text(), nullable=True),
        sa.Column("field_name", sa.String(length=128), nullable=True),
        sa.Column("current_value_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("expected_value_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("status", sa.String(length=32), server_default="new", nullable=False),
        sa.Column("fingerprint", sa.String(length=128), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["wb_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["snapshot_id"], ["card_quality_snapshots.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_card_quality_issues_account_id", "card_quality_issues", ["account_id"])
    op.create_index("ix_card_quality_issues_account_nm", "card_quality_issues", ["account_id", "nm_id"])
    op.create_index("ix_card_quality_issues_account_status_severity", "card_quality_issues", ["account_id", "status", "severity"])
    op.create_index("ix_card_quality_issues_category", "card_quality_issues", ["category"])
    op.create_index("ix_card_quality_issues_fingerprint", "card_quality_issues", ["fingerprint"])
    op.create_index("ix_card_quality_issues_issue_code", "card_quality_issues", ["issue_code"])
    op.create_index("ix_card_quality_issues_last_seen_at", "card_quality_issues", ["last_seen_at"])
    op.create_index("ix_card_quality_issues_nm_id", "card_quality_issues", ["nm_id"])
    op.create_index("ix_card_quality_issues_resolved_at", "card_quality_issues", ["resolved_at"])
    op.create_index("ix_card_quality_issues_severity", "card_quality_issues", ["severity"])
    op.create_index("ix_card_quality_issues_snapshot_id", "card_quality_issues", ["snapshot_id"])
    op.create_index("ix_card_quality_issues_status", "card_quality_issues", ["status"])
    op.execute(
        """
        CREATE UNIQUE INDEX uq_card_quality_issues_active_fingerprint
        ON card_quality_issues (account_id, nm_id, fingerprint)
        WHERE resolved_at IS NULL AND status NOT IN ('done', 'ignored', 'resolved')
        """
    )

    op.create_table(
        "card_quality_issue_status_history",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("account_id", sa.BigInteger(), nullable=False),
        sa.Column("issue_id", sa.BigInteger(), nullable=False),
        sa.Column("old_status", sa.String(length=32), nullable=True),
        sa.Column("new_status", sa.String(length=32), nullable=False),
        sa.Column("changed_by_user_id", sa.BigInteger(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["wb_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["changed_by_user_id"], ["auth_users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["issue_id"], ["card_quality_issues.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_card_quality_issue_status_history_account_id", "card_quality_issue_status_history", ["account_id"])
    op.create_index("ix_card_quality_issue_status_history_account_issue", "card_quality_issue_status_history", ["account_id", "issue_id"])
    op.create_index("ix_card_quality_issue_status_history_changed_by_user_id", "card_quality_issue_status_history", ["changed_by_user_id"])
    op.create_index("ix_card_quality_issue_status_history_issue_id", "card_quality_issue_status_history", ["issue_id"])
    op.create_index("ix_card_quality_issue_status_history_new_status", "card_quality_issue_status_history", ["new_status"])


def downgrade() -> None:
    op.drop_index("ix_card_quality_issue_status_history_new_status", table_name="card_quality_issue_status_history")
    op.drop_index("ix_card_quality_issue_status_history_issue_id", table_name="card_quality_issue_status_history")
    op.drop_index("ix_card_quality_issue_status_history_changed_by_user_id", table_name="card_quality_issue_status_history")
    op.drop_index("ix_card_quality_issue_status_history_account_issue", table_name="card_quality_issue_status_history")
    op.drop_index("ix_card_quality_issue_status_history_account_id", table_name="card_quality_issue_status_history")
    op.drop_table("card_quality_issue_status_history")
    op.execute("DROP INDEX IF EXISTS uq_card_quality_issues_active_fingerprint")
    for name in (
        "ix_card_quality_issues_status",
        "ix_card_quality_issues_snapshot_id",
        "ix_card_quality_issues_severity",
        "ix_card_quality_issues_resolved_at",
        "ix_card_quality_issues_nm_id",
        "ix_card_quality_issues_last_seen_at",
        "ix_card_quality_issues_issue_code",
        "ix_card_quality_issues_fingerprint",
        "ix_card_quality_issues_category",
        "ix_card_quality_issues_account_status_severity",
        "ix_card_quality_issues_account_nm",
        "ix_card_quality_issues_account_id",
    ):
        op.drop_index(name, table_name="card_quality_issues")
    op.drop_table("card_quality_issues")
    for name in (
        "ix_card_quality_snapshots_vendor_code",
        "ix_card_quality_snapshots_status",
        "ix_card_quality_snapshots_source_revision",
        "ix_card_quality_snapshots_source_card_id",
        "ix_card_quality_snapshots_nm_id",
        "ix_card_quality_snapshots_analyzed_at",
        "ix_card_quality_snapshots_account_status",
        "ix_card_quality_snapshots_account_nm",
        "ix_card_quality_snapshots_account_id",
    ):
        op.drop_index(name, table_name="card_quality_snapshots")
    op.drop_table("card_quality_snapshots")
    for name in (
        "ix_card_quality_analysis_runs_status",
        "ix_card_quality_analysis_runs_finished_at",
        "ix_card_quality_analysis_runs_started_at",
        "ix_card_quality_analysis_runs_run_type",
        "ix_card_quality_analysis_runs_requested_by_user_id",
        "ix_card_quality_analysis_runs_account_status",
        "ix_card_quality_analysis_runs_account_started",
        "ix_card_quality_analysis_runs_account_id",
    ):
        op.drop_index(name, table_name="card_quality_analysis_runs")
    op.drop_table("card_quality_analysis_runs")
