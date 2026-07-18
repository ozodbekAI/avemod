"""Add local claims detection runs and candidates.

Revision ID: 20260622_000039
Revises: 20260621_000038
Create Date: 2026-06-22 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260622_000039"
down_revision = "20260621_000038"
branch_labels = None
depends_on = None

JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        "claim_detection_runs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("account_id", sa.BigInteger(), nullable=False),
        sa.Column("detector_type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="queued", nullable=False),
        sa.Column("requested_by_user_id", sa.BigInteger(), nullable=True),
        sa.Column("date_from", sa.Date(), nullable=True),
        sa.Column("date_to", sa.Date(), nullable=True),
        sa.Column("source_snapshot_json", JSONB, server_default="{}", nullable=False),
        sa.Column("cursor_json", JSONB, server_default="{}", nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("candidates_found", sa.Integer(), server_default="0", nullable=False),
        sa.Column("candidates_created", sa.Integer(), server_default="0", nullable=False),
        sa.Column("candidates_updated", sa.Integer(), server_default="0", nullable=False),
        sa.Column("candidates_skipped", sa.Integer(), server_default="0", nullable=False),
        sa.Column("rows_failed", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error_code", sa.String(length=128), nullable=True),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["account_id"], ["wb_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["auth_users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("account_id", "detector_type", "status", "requested_by_user_id", "date_from", "date_to", "started_at", "finished_at", "heartbeat_at"):
        op.create_index(f"ix_claim_detection_runs_{column}", "claim_detection_runs", [column])
    op.create_index("ix_claim_detection_runs_account_detector_started", "claim_detection_runs", ["account_id", "detector_type", "started_at"])
    op.create_index("ix_claim_detection_runs_account_status", "claim_detection_runs", ["account_id", "status"])

    op.create_table(
        "claim_candidates",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("account_id", sa.BigInteger(), nullable=False),
        sa.Column("detector_type", sa.String(length=64), nullable=False),
        sa.Column("source_type", sa.String(length=64), nullable=True),
        sa.Column("source_id", sa.String(length=255), nullable=True),
        sa.Column("external_id", sa.String(length=255), nullable=True),
        sa.Column("external_reference", sa.String(length=255), nullable=True),
        sa.Column("nm_id", sa.BigInteger(), nullable=True),
        sa.Column("sku_id", sa.BigInteger(), nullable=True),
        sa.Column("supply_id", sa.String(length=255), nullable=True),
        sa.Column("report_id", sa.String(length=255), nullable=True),
        sa.Column("order_id", sa.String(length=255), nullable=True),
        sa.Column("sale_id", sa.String(length=255), nullable=True),
        sa.Column("warehouse_id", sa.String(length=255), nullable=True),
        sa.Column("period_from", sa.Date(), nullable=True),
        sa.Column("period_to", sa.Date(), nullable=True),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("business_explanation", sa.Text(), nullable=True),
        sa.Column("reason_code", sa.String(length=128), nullable=True),
        sa.Column("severity", sa.String(length=32), server_default="medium", nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("expected_amount", sa.Numeric(18, 4), nullable=True),
        sa.Column("quantity_affected", sa.Numeric(18, 4), nullable=True),
        sa.Column("status", sa.String(length=32), server_default="new", nullable=False),
        sa.Column("fingerprint", sa.String(length=128), nullable=False),
        sa.Column("evidence_summary_json", JSONB, server_default="{}", nullable=False),
        sa.Column("source_revision", sa.String(length=128), nullable=True),
        sa.Column("detection_run_id", sa.BigInteger(), nullable=True),
        sa.Column("case_id", sa.BigInteger(), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("payload_json", JSONB, server_default="{}", nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["wb_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["case_id"], ["operator_cases.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["detection_run_id"], ["claim_detection_runs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("account_id", "fingerprint", name="uq_claim_candidates_account_fingerprint"),
    )
    for column in ("account_id", "detector_type", "source_type", "source_id", "external_id", "external_reference", "nm_id", "sku_id", "supply_id", "report_id", "order_id", "sale_id", "warehouse_id", "period_from", "period_to", "reason_code", "severity", "confidence", "status", "fingerprint", "detection_run_id", "case_id", "first_seen_at", "last_seen_at", "resolved_at"):
        op.create_index(f"ix_claim_candidates_{column}", "claim_candidates", [column])
    op.create_index("ix_claim_candidates_account_detector_status", "claim_candidates", ["account_id", "detector_type", "status"])
    op.create_index("ix_claim_candidates_account_nm", "claim_candidates", ["account_id", "nm_id"])
    op.create_index("ix_claim_candidates_account_case", "claim_candidates", ["account_id", "case_id"])


def downgrade() -> None:
    op.drop_index("ix_claim_candidates_account_case", table_name="claim_candidates")
    op.drop_index("ix_claim_candidates_account_nm", table_name="claim_candidates")
    op.drop_index("ix_claim_candidates_account_detector_status", table_name="claim_candidates")
    for column in ("resolved_at", "last_seen_at", "first_seen_at", "case_id", "detection_run_id", "fingerprint", "status", "confidence", "severity", "reason_code", "period_to", "period_from", "warehouse_id", "sale_id", "order_id", "report_id", "supply_id", "sku_id", "nm_id", "external_reference", "external_id", "source_id", "source_type", "detector_type", "account_id"):
        op.drop_index(f"ix_claim_candidates_{column}", table_name="claim_candidates")
    op.drop_table("claim_candidates")
    op.drop_index("ix_claim_detection_runs_account_status", table_name="claim_detection_runs")
    op.drop_index("ix_claim_detection_runs_account_detector_started", table_name="claim_detection_runs")
    for column in ("heartbeat_at", "finished_at", "started_at", "date_to", "date_from", "requested_by_user_id", "status", "detector_type", "account_id"):
        op.drop_index(f"ix_claim_detection_runs_{column}", table_name="claim_detection_runs")
    op.drop_table("claim_detection_runs")
