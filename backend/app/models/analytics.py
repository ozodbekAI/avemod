from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, BigIntPKMixin, TimestampMixin


class WBCardFunnelDaily(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "wb_card_funnel_daily"
    __table_args__ = (UniqueConstraint("account_id", "stat_date", "nm_id"),)

    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE")
    )
    stat_date: Mapped[date] = mapped_column(Date, index=True)
    nm_id: Mapped[int] = mapped_column(index=True)
    vendor_code: Mapped[str | None] = mapped_column(String(255), nullable=True)
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    brand_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    subject_id: Mapped[int | None] = mapped_column(nullable=True)
    subject_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    open_count: Mapped[int | None] = mapped_column(nullable=True)
    cart_count: Mapped[int | None] = mapped_column(nullable=True)
    order_count: Mapped[int | None] = mapped_column(nullable=True)
    buyout_count: Mapped[int | None] = mapped_column(nullable=True)
    cancel_count: Mapped[int | None] = mapped_column(nullable=True)
    add_to_cart_conversion: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    cart_to_order_conversion: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    buyout_percent: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)


class WBRegionSalesDaily(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "wb_region_sales_daily"
    __dedupe_fields__ = (
        "account_id",
        "stat_date",
        "country_name",
        "region_name",
        "city_name",
        "nm_id",
        "vendor_code",
    )
    __table_args__ = (
        UniqueConstraint(
            "account_id",
            "stat_date",
            "country_name",
            "region_name",
            "city_name",
            "nm_id",
            "vendor_code",
        ),
    )

    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE")
    )
    dedupe_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    stat_date: Mapped[date] = mapped_column(Date, index=True)
    region_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    country_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    federal_district: Mapped[str | None] = mapped_column(String(255), nullable=True)
    nm_id: Mapped[int | None] = mapped_column(nullable=True, index=True)
    vendor_code: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sale_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    sale_amount_percent: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    sale_quantity: Mapped[int | None] = mapped_column(nullable=True)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)


class WBHiddenProduct(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "wb_hidden_products"

    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE")
    )
    hidden_type: Mapped[str] = mapped_column(String(32), index=True)
    nm_id: Mapped[int | None] = mapped_column(nullable=True, index=True)
    vendor_code: Mapped[str | None] = mapped_column(String(255), nullable=True)
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    reason: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
