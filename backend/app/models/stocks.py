from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, BigIntPKMixin, TimestampMixin


class WBStockSnapshot(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "wb_stock_snapshots"

    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE")
    )
    snapshot_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    source: Mapped[str] = mapped_column(String(64), default="warehouse_remains")
    task_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)


class WBStockSnapshotRow(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "wb_stock_snapshot_rows"

    snapshot_id: Mapped[int] = mapped_column(
        ForeignKey("wb_stock_snapshots.id", ondelete="CASCADE")
    )
    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE")
    )
    nm_id: Mapped[int | None] = mapped_column(nullable=True, index=True)
    barcode: Mapped[str | None] = mapped_column(String(255), nullable=True)
    chrt_id: Mapped[int | None] = mapped_column(nullable=True)
    size_id: Mapped[int | None] = mapped_column(nullable=True)
    warehouse_id: Mapped[int | None] = mapped_column(nullable=True)
    warehouse_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    quantity_full: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    in_way_to_client: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    in_way_from_client: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    subject: Mapped[str | None] = mapped_column(String(255), nullable=True)
    brand: Mapped[str | None] = mapped_column(String(255), nullable=True)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
