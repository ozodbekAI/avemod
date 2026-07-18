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


class WBSale(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "wb_sales"
    __dedupe_fields__ = (
        "account_id",
        "srid",
        "last_change_date",
        "nm_id",
        "barcode",
        "sale_id",
    )
    __table_args__ = (
        UniqueConstraint(
            "account_id",
            "srid",
            "last_change_date",
            "nm_id",
            "barcode",
            "sale_id",
            name="uq_wb_sales_account_srid_change_nm_barcode_sale",
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
    sale_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    order_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    nm_id: Mapped[int | None] = mapped_column(nullable=True, index=True)
    supplier_article: Mapped[str | None] = mapped_column(String(255), nullable=True)
    barcode: Mapped[str | None] = mapped_column(String(255), nullable=True)
    warehouse_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    total_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    discount_percent: Mapped[int | None] = mapped_column(nullable=True)
    price_with_disc: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    finished_price: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    for_pay: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    spp: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    is_supply: Mapped[bool | None] = mapped_column(nullable=True)
    is_realization: Mapped[bool | None] = mapped_column(nullable=True)
    is_cancel: Mapped[bool | None] = mapped_column(nullable=True)
    sticker: Mapped[str | None] = mapped_column(String(255), nullable=True)
    category: Mapped[str | None] = mapped_column(String(255), nullable=True)
    subject: Mapped[str | None] = mapped_column(String(255), nullable=True)
    brand: Mapped[str | None] = mapped_column(String(255), nullable=True)
