from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, BigIntPKMixin, TimestampMixin
from app.models.auth import AuthUser  # noqa: F401 - ensure auth_users table is present in metadata for FK resolution


class ManualCostUpload(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "manual_cost_uploads"

    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE")
    )
    created_by_user_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("auth_users.id", ondelete="SET NULL"),
        nullable=True,
    )
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    rows_total: Mapped[int] = mapped_column(default=0)
    rows_valid: Mapped[int] = mapped_column(default=0)
    rows_invalid: Mapped[int] = mapped_column(default=0)
    status: Mapped[str] = mapped_column(String(32), default="processed")
    error_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    imported_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    summary: Mapped[dict] = mapped_column(JSONB, default=dict)


class ManualCost(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "manual_costs"
    __dedupe_fields__ = (
        "account_id",
        "sku_id",
        "vendor_code",
        "nm_id",
        "barcode",
        "tech_size",
        "valid_from",
    )
    __table_args__ = (
        UniqueConstraint(
            "account_id",
            "vendor_code",
            "nm_id",
            "barcode",
            "tech_size",
            "valid_from",
        ),
    )

    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE")
    )
    dedupe_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    upload_id: Mapped[int | None] = mapped_column(
        ForeignKey("manual_cost_uploads.id", ondelete="SET NULL"),
        nullable=True,
    )
    uploaded_by_user_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("auth_users.id", ondelete="SET NULL"),
        nullable=True,
    )
    sku_id: Mapped[int | None] = mapped_column(
        ForeignKey("core_sku.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    vendor_code: Mapped[str] = mapped_column(String(255), index=True)
    nm_id: Mapped[int | None] = mapped_column(nullable=True, index=True)
    barcode: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    tech_size: Mapped[str | None] = mapped_column(String(50), nullable=True)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    cost_price: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    seller_other_expense: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=0)
    packaging_cost: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=0)
    inbound_logistics_cost: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=0)
    supplier: Mapped[str | None] = mapped_column(String(255), nullable=True)
    currency: Mapped[str] = mapped_column(String(8), default="RUB")
    valid_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    source_file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    uploaded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    match_rule: Mapped[str | None] = mapped_column(String(64), nullable=True)
    cost_source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_ambiguous: Mapped[bool] = mapped_column(default=False)
    is_placeholder: Mapped[bool] = mapped_column(Boolean, default=False)
    is_business_trusted: Mapped[bool] = mapped_column(Boolean, default=True)
    is_supplier_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    supplier_confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    supplier_confirmed_by_user_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("auth_users.id", ondelete="SET NULL"),
        nullable=True,
    )
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
