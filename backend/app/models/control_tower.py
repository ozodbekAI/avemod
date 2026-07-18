from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, BigIntPKMixin, TimestampMixin
from app.models.auth import AuthUser  # noqa: F401


class ActionRecommendation(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "action_recommendations"
    __table_args__ = (
        UniqueConstraint(
            "action_unique_key", name="uq_action_recommendations_action_unique_key"
        ),
        Index(
            "ix_action_recommendations_account_window",
            "account_id",
            "source_date_from",
            "source_date_to",
        ),
        Index(
            "ix_action_recommendations_account_window_status",
            "account_id",
            "source_date_from",
            "source_date_to",
            "status",
        ),
        Index(
            "ix_action_recommendations_account_status_sku",
            "account_id",
            "status",
            "sku_id",
        ),
    )

    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE"), index=True
    )
    sku_id: Mapped[int | None] = mapped_column(
        ForeignKey("core_sku.id", ondelete="SET NULL"), nullable=True, index=True
    )
    nm_id: Mapped[int | None] = mapped_column(nullable=True, index=True)
    vendor_code: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    action_type: Mapped[str] = mapped_column(String(64), index=True)
    priority: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(32), default="new", index=True)
    reason_code: Mapped[str] = mapped_column(String(64), index=True)
    reason: Mapped[str] = mapped_column(Text)
    calculation_basis: Mapped[str | None] = mapped_column(Text, nullable=True)
    expected_effect_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    confidence: Mapped[str] = mapped_column(String(16), default="medium")
    trust_state: Mapped[str] = mapped_column(String(32), default="data_blocked")
    blocked_reasons: Mapped[list] = mapped_column(JSONB, default=list)
    source_date_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    source_date_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    source_snapshot_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    action_unique_key: Mapped[str] = mapped_column(String(255), index=True)
    assigned_to: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("auth_users.id", ondelete="SET NULL"), nullable=True
    )
    deadline_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    user_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)


class ActionRecommendationHistory(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "action_recommendation_history"

    action_id: Mapped[int] = mapped_column(
        ForeignKey("action_recommendations.id", ondelete="CASCADE"), index=True
    )
    previous_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    new_status: Mapped[str] = mapped_column(String(32))
    changed_by_user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("auth_users.id", ondelete="SET NULL"), nullable=True
    )
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)


class AlertEvent(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "alert_events"

    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE"), index=True
    )
    action_id: Mapped[int | None] = mapped_column(
        ForeignKey("action_recommendations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    alert_type: Mapped[str] = mapped_column(String(64), index=True)
    severity: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(32), default="new", index=True)
    title: Mapped[str] = mapped_column(String(255))
    message: Mapped[str] = mapped_column(Text)
    confidence: Mapped[str] = mapped_column(String(16), default="medium")
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    snoozed_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class UserBusinessSetting(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "user_business_settings"
    __table_args__ = (
        UniqueConstraint("account_id", name="uq_user_business_settings_account_id"),
    )

    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE"), index=True
    )
    updated_by_user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("auth_users.id", ondelete="SET NULL"), nullable=True
    )
    settings_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)


class UserBusinessSettingAudit(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "user_business_settings_audit"

    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE"), index=True
    )
    changed_by_user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("auth_users.id", ondelete="SET NULL"), nullable=True
    )
    previous_settings_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    next_settings_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)


class FormulaAuditRun(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "formula_audit_runs"

    account_id: Mapped[int | None] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    scope: Mapped[str] = mapped_column(String(64), default="global")
    status: Mapped[str] = mapped_column(String(32), index=True)
    passed: Mapped[bool] = mapped_column(Boolean, default=False)
    result_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
