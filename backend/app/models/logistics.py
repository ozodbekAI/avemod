from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, BigIntPKMixin, TimestampMixin


class WBLogisticsPaidStorageRow(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "wb_logistics_paid_storage_rows"
    __dedupe_fields__ = (
        "account_id",
        "report_date",
        "nm_id",
        "barcode",
        "warehouse_name",
        "source_row_key",
        "payload",
    )

    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE")
    )
    dedupe_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    report_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    nm_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    vendor_code: Mapped[str | None] = mapped_column(String(255), nullable=True)
    barcode: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    brand: Mapped[str | None] = mapped_column(String(255), nullable=True)
    subject_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    warehouse_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    storage_cost: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(16), nullable=True)
    task_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    source_row_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)


class WBLogisticsAcceptanceReportRow(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "wb_logistics_acceptance_report_rows"
    __dedupe_fields__ = (
        "account_id",
        "operation_date",
        "nm_id",
        "barcode",
        "warehouse_name",
        "operation_name",
        "source_row_key",
        "payload",
    )

    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE")
    )
    dedupe_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    operation_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    nm_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    vendor_code: Mapped[str | None] = mapped_column(String(255), nullable=True)
    barcode: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    brand: Mapped[str | None] = mapped_column(String(255), nullable=True)
    subject_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    warehouse_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    operation_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    acceptance_cost: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    currency: Mapped[str | None] = mapped_column(String(16), nullable=True)
    task_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    source_row_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)


class WBLogisticsTransitTariff(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "wb_logistics_transit_tariffs"
    __dedupe_fields__ = (
        "account_id",
        "collected_at",
        "source_warehouse_id",
        "transit_warehouse_id",
        "destination_warehouse_id",
        "box_type_id",
        "payload",
    )

    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE")
    )
    dedupe_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    source_warehouse_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, index=True
    )
    source_warehouse_name: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    transit_warehouse_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, index=True
    )
    transit_warehouse_name: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    destination_warehouse_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, index=True
    )
    destination_warehouse_name: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    box_type_id: Mapped[int | None] = mapped_column(nullable=True)
    coefficient: Mapped[str | None] = mapped_column(String(64), nullable=True)
    delivery_base: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    delivery_liter: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(16), nullable=True)
    transit_time_days: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    route_label: Mapped[str | None] = mapped_column(String(500), nullable=True)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)


class WBSellerWarehouse(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "wb_seller_warehouses"
    __table_args__ = (UniqueConstraint("account_id", "warehouse_id"),)

    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE")
    )
    warehouse_id: Mapped[int] = mapped_column(BigInteger, index=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    office_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    delivery_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    cargo_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool | None] = mapped_column(nullable=True)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)


class WBSellerWarehouseStock(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "wb_seller_warehouse_stocks"
    __table_args__ = (UniqueConstraint("account_id", "warehouse_id", "chrt_id"),)

    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE")
    )
    warehouse_id: Mapped[int] = mapped_column(BigInteger, index=True)
    warehouse_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    chrt_id: Mapped[int] = mapped_column(BigInteger, index=True)
    nm_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    vendor_code: Mapped[str | None] = mapped_column(String(255), nullable=True)
    barcode: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    reserved: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    in_way: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    updated_at_wb: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
