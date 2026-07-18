from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, BigIntPKMixin, TimestampMixin


class WBAdCampaign(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "wb_ad_campaigns"
    __table_args__ = (UniqueConstraint("account_id", "advert_id"),)

    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE")
    )
    advert_id: Mapped[int] = mapped_column(index=True)
    campaign_type: Mapped[int | None] = mapped_column(nullable=True)
    status: Mapped[int | None] = mapped_column(nullable=True)
    bid_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    change_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)


class WBAdCampaignItem(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "wb_ad_campaign_items"

    campaign_fk_id: Mapped[int] = mapped_column(
        ForeignKey("wb_ad_campaigns.id", ondelete="CASCADE")
    )
    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE")
    )
    nm_id: Mapped[int | None] = mapped_column(nullable=True, index=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)


class WBAdStatsDaily(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "wb_ad_stats_daily"
    __dedupe_fields__ = ("account_id", "advert_id", "stat_date", "nm_id")
    __table_args__ = (
        UniqueConstraint("account_id", "advert_id", "stat_date", "nm_id"),
    )

    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE")
    )
    dedupe_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    advert_id: Mapped[int] = mapped_column(index=True)
    stat_date: Mapped[date] = mapped_column(Date, index=True)
    nm_id: Mapped[int | None] = mapped_column(nullable=True, index=True)
    views: Mapped[int | None] = mapped_column(nullable=True)
    clicks: Mapped[int | None] = mapped_column(nullable=True)
    ctr: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    cpc: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    cpm: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    atbs: Mapped[int | None] = mapped_column(nullable=True)
    orders: Mapped[int | None] = mapped_column(nullable=True)
    shks: Mapped[int | None] = mapped_column(nullable=True)
    sum: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    sum_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)

    @staticmethod
    def _payload_number(payload: dict | None, key: str) -> float | None:
        if not isinstance(payload, dict):
            return None
        value = payload.get(key)
        if value is not None and value != "":
            try:
                return float(value)
            except (TypeError, ValueError):
                return None
        rows = payload.get("payload_rows")
        if isinstance(rows, list):
            total = 0.0
            seen = False
            for row in rows:
                if not isinstance(row, dict):
                    continue
                row_value = row.get(key)
                if row_value is None or row_value == "":
                    continue
                try:
                    total += float(row_value)
                    seen = True
                except (TypeError, ValueError):
                    continue
            if seen:
                return total
        period = payload.get("period")
        if isinstance(period, dict):
            return WBAdStatsDaily._payload_number(period, key)
        return None

    @property
    def cr(self) -> Decimal | None:
        value = self._payload_number(self.payload, "cr")
        if value is not None:
            return Decimal(str(value))
        clicks = self.clicks or 0
        orders = self.orders or 0
        if clicks > 0:
            return Decimal(str(orders * 100 / clicks))
        return None

    @property
    def canceled(self) -> int | None:
        value = self._payload_number(self.payload, "canceled")
        if value is None:
            return None
        return int(value)


class WBAdClusterStat(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "wb_ad_cluster_stats"
    __dedupe_fields__ = ("account_id", "advert_id", "stat_date", "cluster", "nm_id")

    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE")
    )
    dedupe_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    advert_id: Mapped[int] = mapped_column(index=True)
    stat_date: Mapped[date] = mapped_column(Date, index=True)
    cluster: Mapped[str | None] = mapped_column(String(255), nullable=True)
    nm_id: Mapped[int | None] = mapped_column(nullable=True, index=True)
    views: Mapped[int | None] = mapped_column(nullable=True)
    clicks: Mapped[int | None] = mapped_column(nullable=True)
    ctr: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    cpc: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    cpm: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    orders: Mapped[int | None] = mapped_column(nullable=True)
    atbs: Mapped[int | None] = mapped_column(nullable=True)
    sum: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    avg_position: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)

    @property
    def shks(self) -> int | None:
        payload = self.payload if isinstance(self.payload, dict) else {}
        value = payload.get("shks")
        if value is None or value == "":
            return None
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return None
