from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    LargeBinary,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, BigIntPKMixin, TimestampMixin


class StockControlSettings(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "stock_control_settings"
    __table_args__ = (
        UniqueConstraint("account_id", name="uq_stock_control_settings_account"),
    )

    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE"), index=True
    )
    default_il_profile_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    minimum_history_orders: Mapped[int] = mapped_column(default=10, nullable=False)
    max_share_ratio_from_default: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), default=Decimal("3"), nullable=False
    )
    minimum_keep_per_size: Mapped[int] = mapped_column(default=1, nullable=False)
    excluded_regions_json: Mapped[list[str]] = mapped_column(JSONB, default=list)
    ship_all_available_default: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    extra_allocation_method_default: Mapped[str] = mapped_column(
        String(64), default="largest_remainder", nullable=False
    )


class StockControlRun(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "stock_control_runs"
    __table_args__ = (
        Index(
            "ix_stock_control_runs_account_created_id", "account_id", "created_at", "id"
        ),
        Index("ix_stock_control_runs_account_status", "account_id", "status"),
        Index("ix_stock_control_runs_account_run_type", "account_id", "run_type"),
    )

    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE"), index=True
    )
    run_type: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(
        String(32), default="queued", nullable=False, index=True
    )
    source_mode: Mapped[str] = mapped_column(
        String(32), default="finance_db", nullable=False, index=True
    )
    allocation_mode: Mapped[str | None] = mapped_column(
        String(32), nullable=True, index=True
    )
    priority_strategy: Mapped[str | None] = mapped_column(String(64), nullable=True)
    requested_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("auth_users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    date_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    date_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    source_snapshot_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    settings_snapshot_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    input_summary_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    result_summary_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    eligible_products: Mapped[int] = mapped_column(default=0, nullable=False)
    rows_processed: Mapped[int] = mapped_column(default=0, nullable=False)
    rows_created: Mapped[int] = mapped_column(default=0, nullable=False)
    rows_skipped: Mapped[int] = mapped_column(default=0, nullable=False)
    rows_failed: Mapped[int] = mapped_column(default=0, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    heartbeat_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)


class StockControlRegionRow(BigIntPKMixin, Base):
    __tablename__ = "stock_control_region_rows"
    __table_args__ = (
        Index("ix_stock_control_region_rows_run_status", "run_id", "status"),
        Index("ix_stock_control_region_rows_account_nm", "account_id", "nm_id"),
    )

    run_id: Mapped[int] = mapped_column(
        ForeignKey("stock_control_runs.id", ondelete="CASCADE"), index=True
    )
    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE"), index=True
    )
    nm_id: Mapped[int | None] = mapped_column(nullable=True, index=True)
    vendor_code: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    barcode: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    chrt_id: Mapped[int | None] = mapped_column(nullable=True, index=True)
    size_name: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    subject: Mapped[str | None] = mapped_column(String(255), nullable=True)
    brand: Mapped[str | None] = mapped_column(String(255), nullable=True)
    region: Mapped[str] = mapped_column(String(255), index=True)
    warehouse_id: Mapped[int | None] = mapped_column(nullable=True, index=True)
    warehouse_name: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    orders_qty: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), default=0, nullable=False
    )
    local_orders_qty: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), default=0, nullable=False
    )
    region_share: Mapped[Decimal] = mapped_column(
        Numeric(18, 8), default=0, nullable=False
    )
    current_stock_qty: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), default=0, nullable=False
    )
    target_stock_qty: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), default=0, nullable=False
    )
    delta_qty: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), default=0, nullable=False
    )
    status: Mapped[str] = mapped_column(String(32), index=True)
    localization_pct: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    impact_pct: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    distribution_source: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )
    source_metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class StockControlMovement(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "stock_control_movements"
    __table_args__ = (
        Index("ix_stock_control_movements_run_type", "run_id", "movement_type"),
        Index("ix_stock_control_movements_account_nm", "account_id", "nm_id"),
    )

    run_id: Mapped[int] = mapped_column(
        ForeignKey("stock_control_runs.id", ondelete="CASCADE"), index=True
    )
    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE"), index=True
    )
    nm_id: Mapped[int | None] = mapped_column(nullable=True, index=True)
    vendor_code: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    barcode: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    size_name: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    movement_type: Mapped[str] = mapped_column(String(64), index=True)
    donor_region: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    donor_warehouse: Mapped[str | None] = mapped_column(String(255), nullable=True)
    recipient_region: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    recipient_warehouse: Mapped[str | None] = mapped_column(String(255), nullable=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=0, nullable=False)
    priority: Mapped[str] = mapped_column(
        String(8), default="P3", nullable=False, index=True
    )
    reason_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    business_explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[str] = mapped_column(
        String(32), default="medium", nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(32), default="new", nullable=False, index=True
    )


class StockControlHandStockDraft(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "stock_control_hand_stock_drafts"
    __table_args__ = (
        Index(
            "ix_stock_control_hand_stock_drafts_account_status", "account_id", "status"
        ),
    )

    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(
        String(32), default="draft", nullable=False, index=True
    )
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("auth_users.id", ondelete="SET NULL"), nullable=True, index=True
    )


class StockControlHandStockRow(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "stock_control_hand_stock_rows"
    __table_args__ = (
        Index(
            "ix_stock_control_hand_stock_rows_draft_match",
            "draft_id",
            "matching_status",
        ),
        Index("ix_stock_control_hand_stock_rows_account_nm", "account_id", "nm_id"),
    )

    draft_id: Mapped[int] = mapped_column(
        ForeignKey("stock_control_hand_stock_drafts.id", ondelete="CASCADE"), index=True
    )
    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE"), index=True
    )
    nm_id: Mapped[int | None] = mapped_column(nullable=True, index=True)
    vendor_code: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    barcode: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    size_name: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    available_qty: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), default=0, nullable=False
    )
    source_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    matching_status: Mapped[str] = mapped_column(
        String(32), default="pending", nullable=False, index=True
    )
    validation_errors_json: Mapped[list[str]] = mapped_column(JSONB, default=list)


class StockControlImport(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "stock_control_imports"
    __table_args__ = (
        Index("ix_stock_control_imports_account_kind", "account_id", "import_type"),
    )

    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE"), index=True
    )
    import_type: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(
        String(32), default="preview", nullable=False, index=True
    )
    file_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    sheet_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    rows_total: Mapped[int] = mapped_column(default=0, nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("auth_users.id", ondelete="SET NULL"), nullable=True, index=True
    )


class StockControlImportRow(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "stock_control_import_rows"
    __table_args__ = (
        Index("ix_stock_control_import_rows_import", "import_id"),
        Index("ix_stock_control_import_rows_account_nm", "account_id", "nm_id"),
    )

    import_id: Mapped[int] = mapped_column(
        ForeignKey("stock_control_imports.id", ondelete="CASCADE"), index=True
    )
    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE"), index=True
    )
    row_type: Mapped[str] = mapped_column(String(64), index=True)
    nm_id: Mapped[int | None] = mapped_column(nullable=True, index=True)
    vendor_code: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    barcode: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    chrt_id: Mapped[int | None] = mapped_column(nullable=True, index=True)
    size_name: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    region: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    warehouse_id: Mapped[int | None] = mapped_column(nullable=True, index=True)
    warehouse_name: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    orders_qty: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), default=0, nullable=False
    )
    stock_qty: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), default=0, nullable=False
    )
    available_qty: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), default=0, nullable=False
    )
    raw_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


class WarehouseRegionMapping(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "warehouse_region_mappings"
    __table_args__ = (
        UniqueConstraint(
            "warehouse_id",
            "warehouse_name",
            name="uq_warehouse_region_mapping_identity",
        ),
        Index("ix_warehouse_region_mappings_name", "warehouse_name"),
        Index("ix_warehouse_region_mappings_region", "canonical_region"),
    )

    warehouse_id: Mapped[int | None] = mapped_column(nullable=True, index=True)
    warehouse_name: Mapped[str] = mapped_column(String(255), index=True)
    canonical_region: Mapped[str] = mapped_column(String(255), index=True)
    business_region: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source: Mapped[str] = mapped_column(
        String(64), default="seed", nullable=False, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class StockControlExportArtifact(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "stock_control_export_artifacts"
    __table_args__ = (Index("ix_stock_control_export_artifacts_run", "run_id"),)

    run_id: Mapped[int] = mapped_column(
        ForeignKey("stock_control_runs.id", ondelete="CASCADE"), index=True
    )
    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE"), index=True
    )
    artifact_type: Mapped[str] = mapped_column(
        String(64), default="xlsx", nullable=False
    )
    file_name: Mapped[str] = mapped_column(String(500))
    content_type: Mapped[str] = mapped_column(
        String(255),
        default="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        nullable=False,
    )
    content: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
