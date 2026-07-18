from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, BigIntPKMixin, TimestampMixin


class WBOrder(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "wb_orders"
    __dedupe_fields__ = (
        "account_id",
        "srid",
        "last_change_date",
        "nm_id",
        "barcode",
        "order_id",
    )
    __table_args__ = (
        UniqueConstraint(
            "account_id",
            "srid",
            "last_change_date",
            "nm_id",
            "barcode",
            "order_id",
            name="uq_wb_orders_account_srid_change_nm_barcode_order",
        ),
    )

    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE")
    )
    dedupe_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_change_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True
    )
    srid: Mapped[str] = mapped_column(String(255), index=True)
    g_number: Mapped[str | None] = mapped_column(String(255), nullable=True)
    order_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    nm_id: Mapped[int | None] = mapped_column(nullable=True, index=True)
    supplier_article: Mapped[str | None] = mapped_column(String(255), nullable=True)
    barcode: Mapped[str | None] = mapped_column(String(255), nullable=True)
    warehouse_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    warehouse_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    region_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    oblast_okrug_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    country_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    total_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    discount_percent: Mapped[int | None] = mapped_column(nullable=True)
    spp: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    finished_price: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    price_with_disc: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    is_cancel: Mapped[bool | None] = mapped_column(nullable=True)
    cancel_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
