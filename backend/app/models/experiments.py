from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, BigIntPKMixin, TimestampMixin


class ExperimentEvent(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "experiment_events"

    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE"), index=True
    )
    nm_id: Mapped[int] = mapped_column(BigInteger, index=True)
    sku_id: Mapped[int | None] = mapped_column(
        ForeignKey("core_sku.id", ondelete="SET NULL"), nullable=True, index=True
    )
    action_id: Mapped[int | None] = mapped_column(
        ForeignKey("action_recommendations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    before_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    after_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_by: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("auth_users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )


class Experiment(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "experiments"
    __table_args__ = (
        UniqueConstraint(
            "account_id",
            "source_module",
            "source_action_key",
            name="uq_experiments_source_action",
        ),
    )

    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE"), index=True
    )
    nm_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    sku_id: Mapped[int | None] = mapped_column(
        ForeignKey("core_sku.id", ondelete="SET NULL"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    experiment_type: Mapped[str] = mapped_column(
        String(32), default="before_after", nullable=False, index=True
    )
    intervention_type: Mapped[str] = mapped_column(
        String(32), default="manual_other", nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(
        String(32), default="draft", nullable=False, index=True
    )
    hypothesis: Mapped[str] = mapped_column(Text)
    primary_metric: Mapped[str] = mapped_column(
        String(64), default="revenue", nullable=False
    )
    secondary_metrics_json: Mapped[list] = mapped_column(JSONB, default=list)
    guardrail_metrics_json: Mapped[list] = mapped_column(JSONB, default=list)
    baseline_days: Mapped[int] = mapped_column(Integer, default=7, nullable=False)
    post_days: Mapped[int] = mapped_column(Integer, default=7, nullable=False)
    evaluation_delay_days: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    planned_start_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    intervention_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    evaluation_due_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("auth_users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    source_module: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )
    source_action_key: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    source_project_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_test: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, index=True
    )
    baseline_summary_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    progress_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    warnings_json: Mapped[list] = mapped_column(JSONB, default=list)


class ExperimentIntervention(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "experiment_interventions"

    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE"), index=True
    )
    experiment_id: Mapped[int] = mapped_column(
        ForeignKey("experiments.id", ondelete="CASCADE"), index=True
    )
    intervention_type: Mapped[str] = mapped_column(String(32), index=True)
    applied_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    applied_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("auth_users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    application_mode: Mapped[str] = mapped_column(
        String(32), default="manual_record", nullable=False, index=True
    )
    before_reference_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    after_reference_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    change_summary: Mapped[str] = mapped_column(Text)
    external_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    confirmed_by_sync: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class ExperimentMetricSnapshot(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "experiment_metric_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "experiment_id",
            "window_type",
            "metric_date",
            "metric_name",
            name="uq_experiment_metric_snapshot_day",
        ),
    )

    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE"), index=True
    )
    experiment_id: Mapped[int] = mapped_column(
        ForeignKey("experiments.id", ondelete="CASCADE"), index=True
    )
    window_type: Mapped[str] = mapped_column(String(32), index=True)
    metric_date: Mapped[date] = mapped_column(Date, index=True)
    metric_name: Mapped[str] = mapped_column(String(64), index=True)
    metric_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    metric_unit: Mapped[str] = mapped_column(
        String(32), default="number", nullable=False
    )
    source: Mapped[str] = mapped_column(
        String(64), default="mart_sku_daily", nullable=False
    )
    data_status: Mapped[str] = mapped_column(
        String(32), default="ok", nullable=False, index=True
    )
    data_freshness_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    is_complete: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, index=True
    )
    warnings_json: Mapped[list] = mapped_column(JSONB, default=list)


class ExperimentEvaluation(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "experiment_evaluations"

    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE"), index=True
    )
    experiment_id: Mapped[int] = mapped_column(
        ForeignKey("experiments.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(
        String(32), default="ok", nullable=False, index=True
    )
    evaluation_version: Mapped[str] = mapped_column(
        String(32), default="before_after_v1", nullable=False
    )
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    baseline_window_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    post_window_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    primary_result_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    secondary_results_json: Mapped[list] = mapped_column(JSONB, default=list)
    guardrail_results_json: Mapped[list] = mapped_column(JSONB, default=list)
    data_sufficiency_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    confounders_json: Mapped[list] = mapped_column(JSONB, default=list)
    confidence: Mapped[str] = mapped_column(String(16), default="low", nullable=False)
    outcome: Mapped[str] = mapped_column(
        String(32), default="not_enough_data", nullable=False, index=True
    )
    seller_summary: Mapped[str] = mapped_column(Text)
    technical_summary_json: Mapped[dict] = mapped_column(JSONB, default=dict)


class ExperimentSettings(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "experiment_settings"
    __table_args__ = (
        UniqueConstraint("account_id", name="uq_experiment_settings_account"),
    )

    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE"), index=True
    )
    default_baseline_days: Mapped[int] = mapped_column(
        Integer, default=7, nullable=False
    )
    default_post_days: Mapped[int] = mapped_column(Integer, default=7, nullable=False)
    default_evaluation_delay_days: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    minimum_orders: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    minimum_revenue: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), default=0, nullable=False
    )
    minimum_views: Mapped[int | None] = mapped_column(Integer, nullable=True)
    maximum_stockout_days: Mapped[int] = mapped_column(
        Integer, default=1, nullable=False
    )
    allow_overlapping_experiments: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    weekday_matched_baseline: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
