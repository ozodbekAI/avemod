from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, BigIntPKMixin, TimestampMixin


class WBSupplyWarehouse(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "wb_supply_warehouses"
    __table_args__ = (UniqueConstraint("account_id", "warehouse_id"),)

    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE")
    )
    warehouse_id: Mapped[int] = mapped_column(index=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)


class WBSupplyAcceptanceOption(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "wb_supply_acceptance_options"

    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE")
    )
    warehouse_id: Mapped[int | None] = mapped_column(nullable=True, index=True)
    warehouse_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    box_type_id: Mapped[int | None] = mapped_column(nullable=True)
    coefficient: Mapped[str | None] = mapped_column(String(64), nullable=True)
    allow_unload: Mapped[bool | None] = mapped_column(nullable=True)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)


class WBSupply(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "wb_supplies"
    __table_args__ = (UniqueConstraint("account_id", "supply_id"),)

    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE")
    )
    supply_id: Mapped[int] = mapped_column(index=True)
    preorder_id: Mapped[int | None] = mapped_column(nullable=True)
    create_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    supply_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    fact_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status_id: Mapped[int | None] = mapped_column(nullable=True)
    warehouse_id: Mapped[int | None] = mapped_column(nullable=True)
    warehouse_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    actual_warehouse_id: Mapped[int | None] = mapped_column(nullable=True)
    actual_warehouse_name: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    box_type_id: Mapped[int | None] = mapped_column(nullable=True)
    last_enriched_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    goods_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    packages_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)


class WBSupplyGood(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "wb_supply_goods"

    supply_fk_id: Mapped[int] = mapped_column(
        ForeignKey("wb_supplies.id", ondelete="CASCADE")
    )
    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE")
    )
    nm_id: Mapped[int | None] = mapped_column(nullable=True, index=True)
    vendor_code: Mapped[str | None] = mapped_column(String(255), nullable=True)
    barcode: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tech_size: Mapped[str | None] = mapped_column(String(64), nullable=True)
    quantity: Mapped[int | None] = mapped_column(nullable=True)
    accepted_quantity: Mapped[int | None] = mapped_column(nullable=True)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)


class WBSupplyPackage(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "wb_supply_packages"

    supply_fk_id: Mapped[int] = mapped_column(
        ForeignKey("wb_supplies.id", ondelete="CASCADE")
    )
    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE")
    )
    package_code: Mapped[str | None] = mapped_column(String(255), nullable=True)
    quantity: Mapped[int | None] = mapped_column(nullable=True)
    barcodes: Mapped[list] = mapped_column(JSONB, default=list)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
