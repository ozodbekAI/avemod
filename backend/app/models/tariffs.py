from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, BigIntPKMixin, TimestampMixin


class WBTariffCommission(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "wb_tariff_commissions"
    __dedupe_fields__ = (
        "account_id",
        "collected_at",
        "parent_id",
        "subject_id",
        "payload",
    )

    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE")
    )
    dedupe_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    collected_at: Mapped[date] = mapped_column(Date, index=True)
    parent_id: Mapped[int | None] = mapped_column(nullable=True)
    parent_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    subject_id: Mapped[int | None] = mapped_column(nullable=True)
    subject_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    kgvp_marketplace: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)


class WBTariffBox(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "wb_tariff_boxes"
    __dedupe_fields__ = ("account_id", "collected_at", "warehouse_name", "payload")

    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE")
    )
    dedupe_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    collected_at: Mapped[date] = mapped_column(Date, index=True)
    warehouse_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)


class WBTariffPallet(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "wb_tariff_pallets"
    __dedupe_fields__ = ("account_id", "collected_at", "warehouse_name", "payload")

    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE")
    )
    dedupe_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    collected_at: Mapped[date] = mapped_column(Date, index=True)
    warehouse_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)


class WBTariffReturn(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "wb_tariff_returns"
    __dedupe_fields__ = ("account_id", "collected_at", "warehouse_name", "payload")

    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE")
    )
    dedupe_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    collected_at: Mapped[date] = mapped_column(Date, index=True)
    warehouse_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)


class WBTariffAcceptance(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "wb_tariff_acceptance"
    __dedupe_fields__ = (
        "account_id",
        "collected_at",
        "warehouse_id",
        "warehouse_name",
        "coefficient",
        "payload",
    )

    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE")
    )
    dedupe_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    collected_at: Mapped[date] = mapped_column(Date, index=True)
    warehouse_id: Mapped[int | None] = mapped_column(nullable=True)
    warehouse_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    coefficient: Mapped[str | None] = mapped_column(String(64), nullable=True)
    allow_unload: Mapped[bool | None] = mapped_column(nullable=True)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
