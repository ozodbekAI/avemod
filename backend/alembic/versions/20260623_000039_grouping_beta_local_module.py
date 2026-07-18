"""Add local grouping beta module tables.

Revision ID: 20260623_000039
Revises: 20260622_000039
Create Date: 2026-06-23 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260623_000039"
down_revision = "20260622_000039"
branch_labels = None
depends_on = None

JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        "grouping_settings",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("account_id", sa.BigInteger(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("mode", sa.String(length=32), nullable=False),
        sa.Column("default_scenario", sa.String(length=64), nullable=False),
        sa.Column("minimum_confidence", sa.Numeric(18, 4), nullable=False),
        sa.Column("maximum_risk", sa.Numeric(18, 4), nullable=False),
        sa.Column("allow_cross_brand", sa.Boolean(), nullable=False),
        sa.Column("allow_cross_subject", sa.Boolean(), nullable=False),
        sa.Column("require_color_compatibility", sa.Boolean(), nullable=False),
        sa.Column("require_identity_evidence", sa.Boolean(), nullable=False),
        sa.Column("include_low_data_products", sa.Boolean(), nullable=False),
        sa.Column("scenario_settings_json", JSONB, nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["wb_accounts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("account_id", name="uq_grouping_settings_account"),
    )
    op.create_index("ix_grouping_settings_account_id", "grouping_settings", ["account_id"])

    op.create_table(
        "grouping_runs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("account_id", sa.BigInteger(), nullable=False),
        sa.Column("scenario", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("requested_by_user_id", sa.BigInteger(), nullable=True),
        sa.Column("source_revision", sa.String(length=64), nullable=True),
        sa.Column("cursor_json", JSONB, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("eligible_products", sa.Integer(), nullable=False),
        sa.Column("products_processed", sa.Integer(), nullable=False),
        sa.Column("products_skipped", sa.Integer(), nullable=False),
        sa.Column("products_failed", sa.Integer(), nullable=False),
        sa.Column("candidate_pairs", sa.Integer(), nullable=False),
        sa.Column("candidate_groups", sa.Integer(), nullable=False),
        sa.Column("recommendations_created", sa.Integer(), nullable=False),
        sa.Column("recommendations_updated", sa.Integer(), nullable=False),
        sa.Column("recommendations_rejected_by_constraints", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(length=128), nullable=True),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("settings_snapshot_json", JSONB, nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["wb_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["auth_users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_grouping_runs_account_created_id", "grouping_runs", ["account_id", "created_at", "id"])
    op.create_index("ix_grouping_runs_account_scenario", "grouping_runs", ["account_id", "scenario"])
    op.create_index("ix_grouping_runs_account_status", "grouping_runs", ["account_id", "status"])
    for column in ("account_id", "scenario", "status", "requested_by_user_id"):
        op.create_index(f"ix_grouping_runs_{column}", "grouping_runs", [column])

    op.create_table(
        "grouping_product_snapshots",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("account_id", sa.BigInteger(), nullable=False),
        sa.Column("run_id", sa.BigInteger(), nullable=False),
        sa.Column("nm_id", sa.BigInteger(), nullable=False),
        sa.Column("imt_id", sa.BigInteger(), nullable=True),
        sa.Column("vendor_code", sa.String(length=255), nullable=True),
        sa.Column("article_core", sa.String(length=255), nullable=True),
        sa.Column("article_base_core", sa.String(length=255), nullable=True),
        sa.Column("title", sa.String(length=500), nullable=True),
        sa.Column("brand", sa.String(length=255), nullable=True),
        sa.Column("subject_name", sa.String(length=255), nullable=True),
        sa.Column("color_normalized", sa.String(length=128), nullable=True),
        sa.Column("characteristics_json", JSONB, nullable=False),
        sa.Column("sizes_json", JSONB, nullable=False),
        sa.Column("barcodes_json", JSONB, nullable=False),
        sa.Column("media_summary_json", JSONB, nullable=False),
        sa.Column("stock_summary_json", JSONB, nullable=False),
        sa.Column("finance_summary_json", JSONB, nullable=False),
        sa.Column("source_revision", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["wb_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["grouping_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("account_id", "run_id", "nm_id", name="uq_grouping_snapshots_account_run_nm"),
    )
    op.create_index("ix_grouping_snapshots_account_nm", "grouping_product_snapshots", ["account_id", "nm_id"])
    op.create_index("ix_grouping_snapshots_run", "grouping_product_snapshots", ["run_id"])
    for column in ("account_id", "run_id", "nm_id", "imt_id", "vendor_code", "article_core", "article_base_core", "brand", "subject_name", "color_normalized"):
        op.create_index(f"ix_grouping_product_snapshots_{column}", "grouping_product_snapshots", [column])

    op.create_table(
        "grouping_candidates",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("account_id", sa.BigInteger(), nullable=False),
        sa.Column("run_id", sa.BigInteger(), nullable=False),
        sa.Column("candidate_key", sa.String(length=255), nullable=False),
        sa.Column("anchor_nm_id", sa.BigInteger(), nullable=False),
        sa.Column("member_nm_ids_json", JSONB, nullable=False),
        sa.Column("scenario", sa.String(length=64), nullable=False),
        sa.Column("candidate_type", sa.String(length=64), nullable=False),
        sa.Column("confidence", sa.Numeric(18, 4), nullable=False),
        sa.Column("risk_level", sa.String(length=32), nullable=False),
        sa.Column("risk_score", sa.Numeric(18, 4), nullable=False),
        sa.Column("reasons_json", JSONB, nullable=False),
        sa.Column("risk_reasons_json", JSONB, nullable=False),
        sa.Column("conflicts_json", JSONB, nullable=False),
        sa.Column("evidence_json", JSONB, nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reviewed_by_user_id", sa.BigInteger(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_comment", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["account_id"], ["wb_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["grouping_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reviewed_by_user_id"], ["auth_users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("account_id", "scenario", "fingerprint", name="uq_grouping_candidates_account_scenario_fingerprint"),
    )
    op.create_index("ix_grouping_candidates_account_anchor", "grouping_candidates", ["account_id", "anchor_nm_id"])
    op.create_index("ix_grouping_candidates_account_status", "grouping_candidates", ["account_id", "status"])
    op.create_index("ix_grouping_candidates_run", "grouping_candidates", ["run_id"])
    for column in ("account_id", "run_id", "candidate_key", "anchor_nm_id", "scenario", "risk_level", "status", "fingerprint", "reviewed_by_user_id"):
        op.create_index(f"ix_grouping_candidates_{column}", "grouping_candidates", [column])

    op.create_table(
        "grouping_recommendations",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("account_id", sa.BigInteger(), nullable=False),
        sa.Column("candidate_id", sa.BigInteger(), nullable=False),
        sa.Column("recommendation_type", sa.String(length=64), nullable=False),
        sa.Column("source_nm_id", sa.BigInteger(), nullable=False),
        sa.Column("target_group_key", sa.String(length=255), nullable=False),
        sa.Column("target_imt_id", sa.BigInteger(), nullable=True),
        sa.Column("proposed_members_json", JSONB, nullable=False),
        sa.Column("preview_payload_json", JSONB, nullable=False),
        sa.Column("expected_effect_json", JSONB, nullable=False),
        sa.Column("confidence", sa.Numeric(18, 4), nullable=False),
        sa.Column("risk_level", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["wb_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["candidate_id"], ["grouping_candidates.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_grouping_recommendations_candidate", "grouping_recommendations", ["candidate_id"])
    for column in ("account_id", "candidate_id", "source_nm_id", "status"):
        op.create_index(f"ix_grouping_recommendations_{column}", "grouping_recommendations", [column])

    op.create_table(
        "grouping_review_history",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("account_id", sa.BigInteger(), nullable=False),
        sa.Column("candidate_id", sa.BigInteger(), nullable=False),
        sa.Column("old_status", sa.String(length=32), nullable=True),
        sa.Column("new_status", sa.String(length=32), nullable=False),
        sa.Column("actor_user_id", sa.BigInteger(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["wb_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["candidate_id"], ["grouping_candidates.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["auth_users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_grouping_review_history_candidate", "grouping_review_history", ["candidate_id"])
    for column in ("account_id", "candidate_id", "actor_user_id"):
        op.create_index(f"ix_grouping_review_history_{column}", "grouping_review_history", [column])

    op.create_table(
        "grouping_export_artifacts",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("account_id", sa.BigInteger(), nullable=False),
        sa.Column("run_id", sa.BigInteger(), nullable=False),
        sa.Column("artifact_type", sa.String(length=64), nullable=False),
        sa.Column("storage_key", sa.String(length=500), nullable=False),
        sa.Column("checksum", sa.String(length=128), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["account_id"], ["wb_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["grouping_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_grouping_export_artifacts_run", "grouping_export_artifacts", ["run_id"])
    for column in ("account_id", "run_id", "artifact_type"):
        op.create_index(f"ix_grouping_export_artifacts_{column}", "grouping_export_artifacts", [column])


def downgrade() -> None:
    for column in ("account_id", "run_id", "artifact_type"):
        op.drop_index(f"ix_grouping_export_artifacts_{column}", table_name="grouping_export_artifacts")
    op.drop_index("ix_grouping_export_artifacts_run", table_name="grouping_export_artifacts")
    op.drop_table("grouping_export_artifacts")

    for column in ("account_id", "candidate_id", "actor_user_id"):
        op.drop_index(f"ix_grouping_review_history_{column}", table_name="grouping_review_history")
    op.drop_index("ix_grouping_review_history_candidate", table_name="grouping_review_history")
    op.drop_table("grouping_review_history")

    for column in ("account_id", "candidate_id", "source_nm_id", "status"):
        op.drop_index(f"ix_grouping_recommendations_{column}", table_name="grouping_recommendations")
    op.drop_index("ix_grouping_recommendations_candidate", table_name="grouping_recommendations")
    op.drop_table("grouping_recommendations")

    for column in ("account_id", "run_id", "candidate_key", "anchor_nm_id", "scenario", "risk_level", "status", "fingerprint", "reviewed_by_user_id"):
        op.drop_index(f"ix_grouping_candidates_{column}", table_name="grouping_candidates")
    op.drop_index("ix_grouping_candidates_run", table_name="grouping_candidates")
    op.drop_index("ix_grouping_candidates_account_status", table_name="grouping_candidates")
    op.drop_index("ix_grouping_candidates_account_anchor", table_name="grouping_candidates")
    op.drop_table("grouping_candidates")

    for column in ("account_id", "run_id", "nm_id", "imt_id", "vendor_code", "article_core", "article_base_core", "brand", "subject_name", "color_normalized"):
        op.drop_index(f"ix_grouping_product_snapshots_{column}", table_name="grouping_product_snapshots")
    op.drop_index("ix_grouping_snapshots_run", table_name="grouping_product_snapshots")
    op.drop_index("ix_grouping_snapshots_account_nm", table_name="grouping_product_snapshots")
    op.drop_table("grouping_product_snapshots")

    for column in ("account_id", "scenario", "status", "requested_by_user_id"):
        op.drop_index(f"ix_grouping_runs_{column}", table_name="grouping_runs")
    op.drop_index("ix_grouping_runs_account_status", table_name="grouping_runs")
    op.drop_index("ix_grouping_runs_account_scenario", table_name="grouping_runs")
    op.drop_index("ix_grouping_runs_account_created_id", table_name="grouping_runs")
    op.drop_table("grouping_runs")

    op.drop_index("ix_grouping_settings_account_id", table_name="grouping_settings")
    op.drop_table("grouping_settings")
