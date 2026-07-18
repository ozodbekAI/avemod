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


class WBRealizationReport(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "wb_realization_reports"
    __table_args__ = (UniqueConstraint("account_id", "report_id"),)

    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE")
    )
    report_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    report_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    period: Mapped[str | None] = mapped_column(String(32), nullable=True)
    date_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    date_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    create_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)


class WBRealizationReportRow(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "wb_realization_report_rows"
    __table_args__ = (UniqueConstraint("account_id", "rrd_id"),)

    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE")
    )
    report_id_fk: Mapped[int | None] = mapped_column(
        ForeignKey("wb_realization_reports.id", ondelete="SET NULL"),
        nullable=True,
    )
    rrd_id: Mapped[int] = mapped_column(BigInteger, index=True)
    rr_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    sale_dt: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    order_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    srid: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    shk_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    nm_id: Mapped[int | None] = mapped_column(nullable=True, index=True)
    report_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    doc_type_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    operation_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_sale_operation: Mapped[bool | None] = mapped_column(nullable=True)
    is_return_operation: Mapped[bool | None] = mapped_column(nullable=True)
    is_expense_operation: Mapped[bool | None] = mapped_column(nullable=True)
    is_reconcilable: Mapped[bool | None] = mapped_column(nullable=True)
    quantity: Mapped[int | None] = mapped_column(nullable=True)
    vendor_code: Mapped[str | None] = mapped_column(String(255), nullable=True)
    barcode: Mapped[str | None] = mapped_column(String(255), nullable=True)
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    brand: Mapped[str | None] = mapped_column(String(255), nullable=True)
    subject_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    office_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    seller_oper_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    bonus_type_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    retail_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    retail_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    retail_price_with_disc: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    delivery_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    delivery_service: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    paid_acceptance: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    additional_payment: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    rebill_logistic_cost: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    return_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    ppvz_sales_commission: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    acquiring_fee: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    paid_storage: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    penalty: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    deduction: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    for_pay: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)


class WBAcquiringReport(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "wb_acquiring_reports"
    __table_args__ = (UniqueConstraint("account_id", "report_id"),)

    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE")
    )
    report_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    date_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    date_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    create_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)


class WBAcquiringReportRow(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "wb_acquiring_report_rows"
    __dedupe_fields__ = (
        "account_id",
        "report_id",
        "order_id",
        "srid",
        "shk_id",
        "nm_id",
    )
    __table_args__ = (
        UniqueConstraint(
            "account_id", "report_id", "order_id", "srid", "shk_id", "nm_id"
        ),
    )

    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE")
    )
    dedupe_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    report_id_fk: Mapped[int | None] = mapped_column(
        ForeignKey("wb_acquiring_reports.id", ondelete="SET NULL"),
        nullable=True,
    )
    report_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    order_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    srid: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    shk_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    nm_id: Mapped[int | None] = mapped_column(nullable=True, index=True)
    retail_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    acquiring_fee: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)


class WBBalanceSnapshot(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "wb_balance_snapshots"

    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE")
    )
    snapshot_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    current: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    for_withdraw: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
