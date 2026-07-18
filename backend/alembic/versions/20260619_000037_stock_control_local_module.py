"""Add local stock control module.

Revision ID: 20260619_000037
Revises: 20260619_000036
Create Date: 2026-06-19 13:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260619_000037"
down_revision = "20260619_000036"
branch_labels = None
depends_on = None


JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        "stock_control_settings",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("account_id", sa.BigInteger(), nullable=False),
        sa.Column("default_il_profile_json", JSONB, nullable=False),
        sa.Column("minimum_history_orders", sa.Integer(), nullable=False),
        sa.Column("max_share_ratio_from_default", sa.Numeric(18, 4), nullable=False),
        sa.Column("minimum_keep_per_size", sa.Integer(), nullable=False),
        sa.Column("excluded_regions_json", JSONB, nullable=False),
        sa.Column("ship_all_available_default", sa.Boolean(), nullable=False),
        sa.Column("extra_allocation_method_default", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["wb_accounts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("account_id", name="uq_stock_control_settings_account"),
    )
    op.create_index("ix_stock_control_settings_account_id", "stock_control_settings", ["account_id"])

    op.create_table(
        "stock_control_runs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("account_id", sa.BigInteger(), nullable=False),
        sa.Column("run_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("source_mode", sa.String(length=32), nullable=False),
        sa.Column("allocation_mode", sa.String(length=32), nullable=True),
        sa.Column("priority_strategy", sa.String(length=64), nullable=True),
        sa.Column("requested_by_user_id", sa.BigInteger(), nullable=True),
        sa.Column("date_from", sa.Date(), nullable=True),
        sa.Column("date_to", sa.Date(), nullable=True),
        sa.Column("source_snapshot_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("settings_snapshot_json", JSONB, nullable=False),
        sa.Column("input_summary_json", JSONB, nullable=False),
        sa.Column("result_summary_json", JSONB, nullable=False),
        sa.Column("eligible_products", sa.Integer(), nullable=False),
        sa.Column("rows_processed", sa.Integer(), nullable=False),
        sa.Column("rows_created", sa.Integer(), nullable=False),
        sa.Column("rows_skipped", sa.Integer(), nullable=False),
        sa.Column("rows_failed", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(length=128), nullable=True),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["account_id"], ["wb_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["auth_users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_stock_control_runs_account_created_id", "stock_control_runs", ["account_id", "created_at", "id"])
    op.create_index("ix_stock_control_runs_account_run_type", "stock_control_runs", ["account_id", "run_type"])
    op.create_index("ix_stock_control_runs_account_status", "stock_control_runs", ["account_id", "status"])
    op.create_index("ix_stock_control_runs_account_id", "stock_control_runs", ["account_id"])
    op.create_index("ix_stock_control_runs_requested_by_user_id", "stock_control_runs", ["requested_by_user_id"])
    op.create_index("ix_stock_control_runs_run_type", "stock_control_runs", ["run_type"])
    op.create_index("ix_stock_control_runs_status", "stock_control_runs", ["status"])
    op.create_index("ix_stock_control_runs_source_mode", "stock_control_runs", ["source_mode"])
    op.create_index("ix_stock_control_runs_allocation_mode", "stock_control_runs", ["allocation_mode"])

    op.create_table(
        "stock_control_region_rows",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.BigInteger(), nullable=False),
        sa.Column("account_id", sa.BigInteger(), nullable=False),
        sa.Column("nm_id", sa.BigInteger(), nullable=True),
        sa.Column("vendor_code", sa.String(length=255), nullable=True),
        sa.Column("barcode", sa.String(length=255), nullable=True),
        sa.Column("chrt_id", sa.BigInteger(), nullable=True),
        sa.Column("size_name", sa.String(length=64), nullable=True),
        sa.Column("subject", sa.String(length=255), nullable=True),
        sa.Column("brand", sa.String(length=255), nullable=True),
        sa.Column("region", sa.String(length=255), nullable=False),
        sa.Column("warehouse_id", sa.BigInteger(), nullable=True),
        sa.Column("warehouse_name", sa.String(length=255), nullable=True),
        sa.Column("orders_qty", sa.Numeric(18, 4), nullable=False),
        sa.Column("local_orders_qty", sa.Numeric(18, 4), nullable=False),
        sa.Column("region_share", sa.Numeric(18, 8), nullable=False),
        sa.Column("current_stock_qty", sa.Numeric(18, 4), nullable=False),
        sa.Column("target_stock_qty", sa.Numeric(18, 4), nullable=False),
        sa.Column("delta_qty", sa.Numeric(18, 4), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("localization_pct", sa.Numeric(18, 4), nullable=True),
        sa.Column("impact_pct", sa.Numeric(18, 4), nullable=True),
        sa.Column("distribution_source", sa.String(length=64), nullable=True),
        sa.Column("source_metadata_json", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["wb_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["stock_control_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_stock_control_region_rows_run_status", "stock_control_region_rows", ["run_id", "status"])
    op.create_index("ix_stock_control_region_rows_account_nm", "stock_control_region_rows", ["account_id", "nm_id"])
    for column in ("run_id", "account_id", "nm_id", "vendor_code", "barcode", "chrt_id", "size_name", "region", "warehouse_id", "warehouse_name", "status", "distribution_source"):
        op.create_index(f"ix_stock_control_region_rows_{column}", "stock_control_region_rows", [column])

    op.create_table(
        "stock_control_movements",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("run_id", sa.BigInteger(), nullable=False),
        sa.Column("account_id", sa.BigInteger(), nullable=False),
        sa.Column("nm_id", sa.BigInteger(), nullable=True),
        sa.Column("vendor_code", sa.String(length=255), nullable=True),
        sa.Column("barcode", sa.String(length=255), nullable=True),
        sa.Column("size_name", sa.String(length=64), nullable=True),
        sa.Column("movement_type", sa.String(length=64), nullable=False),
        sa.Column("donor_region", sa.String(length=255), nullable=True),
        sa.Column("donor_warehouse", sa.String(length=255), nullable=True),
        sa.Column("recipient_region", sa.String(length=255), nullable=True),
        sa.Column("recipient_warehouse", sa.String(length=255), nullable=True),
        sa.Column("quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("priority", sa.String(length=8), nullable=False),
        sa.Column("reason_code", sa.String(length=128), nullable=True),
        sa.Column("business_explanation", sa.Text(), nullable=True),
        sa.Column("confidence", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["wb_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["stock_control_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_stock_control_movements_run_type", "stock_control_movements", ["run_id", "movement_type"])
    op.create_index("ix_stock_control_movements_account_nm", "stock_control_movements", ["account_id", "nm_id"])
    for column in ("run_id", "account_id", "nm_id", "vendor_code", "barcode", "size_name", "movement_type", "donor_region", "recipient_region", "priority", "status"):
        op.create_index(f"ix_stock_control_movements_{column}", "stock_control_movements", [column])

    op.create_table(
        "stock_control_hand_stock_drafts",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("account_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_by_user_id", sa.BigInteger(), nullable=True),
        sa.ForeignKeyConstraint(["account_id"], ["wb_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["auth_users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_stock_control_hand_stock_drafts_account_status", "stock_control_hand_stock_drafts", ["account_id", "status"])
    op.create_index("ix_stock_control_hand_stock_drafts_account_id", "stock_control_hand_stock_drafts", ["account_id"])
    op.create_index("ix_stock_control_hand_stock_drafts_status", "stock_control_hand_stock_drafts", ["status"])
    op.create_index("ix_stock_control_hand_stock_drafts_created_by_user_id", "stock_control_hand_stock_drafts", ["created_by_user_id"])

    op.create_table(
        "stock_control_hand_stock_rows",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("draft_id", sa.BigInteger(), nullable=False),
        sa.Column("account_id", sa.BigInteger(), nullable=False),
        sa.Column("nm_id", sa.BigInteger(), nullable=True),
        sa.Column("vendor_code", sa.String(length=255), nullable=True),
        sa.Column("barcode", sa.String(length=255), nullable=True),
        sa.Column("size_name", sa.String(length=64), nullable=True),
        sa.Column("available_qty", sa.Numeric(18, 4), nullable=False),
        sa.Column("source_name", sa.String(length=255), nullable=True),
        sa.Column("matching_status", sa.String(length=32), nullable=False),
        sa.Column("validation_errors_json", JSONB, nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["wb_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["draft_id"], ["stock_control_hand_stock_drafts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_stock_control_hand_stock_rows_draft_match", "stock_control_hand_stock_rows", ["draft_id", "matching_status"])
    op.create_index("ix_stock_control_hand_stock_rows_account_nm", "stock_control_hand_stock_rows", ["account_id", "nm_id"])
    for column in ("draft_id", "account_id", "nm_id", "vendor_code", "barcode", "size_name", "matching_status"):
        op.create_index(f"ix_stock_control_hand_stock_rows_{column}", "stock_control_hand_stock_rows", [column])

    op.create_table(
        "stock_control_imports",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("account_id", sa.BigInteger(), nullable=False),
        sa.Column("import_type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("file_name", sa.String(length=500), nullable=True),
        sa.Column("sheet_name", sa.String(length=255), nullable=True),
        sa.Column("rows_total", sa.Integer(), nullable=False),
        sa.Column("metadata_json", JSONB, nullable=False),
        sa.Column("created_by_user_id", sa.BigInteger(), nullable=True),
        sa.ForeignKeyConstraint(["account_id"], ["wb_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["auth_users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_stock_control_imports_account_kind", "stock_control_imports", ["account_id", "import_type"])
    for column in ("account_id", "import_type", "status", "created_by_user_id"):
        op.create_index(f"ix_stock_control_imports_{column}", "stock_control_imports", [column])

    op.create_table(
        "stock_control_import_rows",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("import_id", sa.BigInteger(), nullable=False),
        sa.Column("account_id", sa.BigInteger(), nullable=False),
        sa.Column("row_type", sa.String(length=64), nullable=False),
        sa.Column("nm_id", sa.BigInteger(), nullable=True),
        sa.Column("vendor_code", sa.String(length=255), nullable=True),
        sa.Column("barcode", sa.String(length=255), nullable=True),
        sa.Column("chrt_id", sa.BigInteger(), nullable=True),
        sa.Column("size_name", sa.String(length=64), nullable=True),
        sa.Column("region", sa.String(length=255), nullable=True),
        sa.Column("warehouse_id", sa.BigInteger(), nullable=True),
        sa.Column("warehouse_name", sa.String(length=255), nullable=True),
        sa.Column("orders_qty", sa.Numeric(18, 4), nullable=False),
        sa.Column("stock_qty", sa.Numeric(18, 4), nullable=False),
        sa.Column("available_qty", sa.Numeric(18, 4), nullable=False),
        sa.Column("raw_json", JSONB, nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["wb_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["import_id"], ["stock_control_imports.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_stock_control_import_rows_import", "stock_control_import_rows", ["import_id"])
    op.create_index("ix_stock_control_import_rows_account_nm", "stock_control_import_rows", ["account_id", "nm_id"])
    for column in ("import_id", "account_id", "row_type", "nm_id", "vendor_code", "barcode", "chrt_id", "size_name", "region", "warehouse_id", "warehouse_name"):
        op.create_index(f"ix_stock_control_import_rows_{column}", "stock_control_import_rows", [column])

    op.create_table(
        "warehouse_region_mappings",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("warehouse_id", sa.BigInteger(), nullable=True),
        sa.Column("warehouse_name", sa.String(length=255), nullable=False),
        sa.Column("canonical_region", sa.String(length=255), nullable=False),
        sa.Column("business_region", sa.String(length=255), nullable=True),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("warehouse_id", "warehouse_name", name="uq_warehouse_region_mapping_identity"),
    )
    op.create_index("ix_warehouse_region_mappings_name", "warehouse_region_mappings", ["warehouse_name"])
    op.create_index("ix_warehouse_region_mappings_region", "warehouse_region_mappings", ["canonical_region"])
    op.create_index("ix_warehouse_region_mappings_warehouse_id", "warehouse_region_mappings", ["warehouse_id"])
    op.create_index("ix_warehouse_region_mappings_warehouse_name", "warehouse_region_mappings", ["warehouse_name"])
    op.create_index("ix_warehouse_region_mappings_canonical_region", "warehouse_region_mappings", ["canonical_region"])
    op.create_index("ix_warehouse_region_mappings_source", "warehouse_region_mappings", ["source"])

    op.create_table(
        "stock_control_export_artifacts",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("run_id", sa.BigInteger(), nullable=False),
        sa.Column("account_id", sa.BigInteger(), nullable=False),
        sa.Column("artifact_type", sa.String(length=64), nullable=False),
        sa.Column("file_name", sa.String(length=500), nullable=False),
        sa.Column("content_type", sa.String(length=255), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=True),
        sa.Column("metadata_json", JSONB, nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["wb_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["stock_control_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_stock_control_export_artifacts_run", "stock_control_export_artifacts", ["run_id"])
    op.create_index("ix_stock_control_export_artifacts_account_id", "stock_control_export_artifacts", ["account_id"])


def downgrade() -> None:
    for table in (
        "stock_control_export_artifacts",
        "warehouse_region_mappings",
        "stock_control_import_rows",
        "stock_control_imports",
        "stock_control_hand_stock_rows",
        "stock_control_hand_stock_drafts",
        "stock_control_movements",
        "stock_control_region_rows",
        "stock_control_runs",
        "stock_control_settings",
    ):
        op.drop_table(table)
