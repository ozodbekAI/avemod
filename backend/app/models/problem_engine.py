from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, BigIntPKMixin, TimestampMixin


class MetricCatalog(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "metric_catalog"
    __table_args__ = (
        UniqueConstraint("metric_code", name="uq_metric_catalog_metric_code"),
        Index("ix_metric_catalog_metric_code", "metric_code"),
    )

    metric_code: Mapped[str] = mapped_column(String(128), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    value_type: Mapped[str] = mapped_column(String(32), nullable=False)
    unit: Mapped[str | None] = mapped_column(String(64), nullable=True)
    grain: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_module: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    formula_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    source_tables_json: Mapped[list[str]] = mapped_column(
        JSONB, default=list, nullable=False
    )
    source_endpoints_json: Mapped[list[str]] = mapped_column(
        JSONB, default=list, nullable=False
    )
    required_metrics_json: Mapped[list[str]] = mapped_column(
        JSONB, default=list, nullable=False
    )
    trust_state: Mapped[str] = mapped_column(
        String(32), default="provisional", nullable=False, index=True
    )
    is_admin_visible: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, index=True
    )
    is_deprecated: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, index=True
    )


class ProblemDefinition(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "problem_definitions"
    __table_args__ = (
        UniqueConstraint("problem_code", name="uq_problem_definitions_problem_code"),
        Index("ix_problem_definitions_problem_code", "problem_code"),
        Index("ix_problem_definitions_system_seeded", "is_system_seeded"),
    )

    problem_code: Mapped[str] = mapped_column(String(128), nullable=False)
    source_module: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    title_template: Mapped[str] = mapped_column(Text, nullable=False)
    description_template: Mapped[str] = mapped_column(Text, nullable=False)
    recommendation_template: Mapped[str] = mapped_column(Text, nullable=False)
    impact_type_default: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True
    )
    trust_state_default: Mapped[str] = mapped_column(
        String(32), default="provisional", nullable=False, index=True
    )
    severity_default: Mapped[str] = mapped_column(
        String(32), default="medium", nullable=False, index=True
    )
    allowed_actions_json: Mapped[list[str]] = mapped_column(
        JSONB, default=list, nullable=False
    )
    test_only: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, index=True
    )
    seller_visible: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, index=True
    )
    visibility_mode: Mapped[str] = mapped_column(
        String(32), default="seller", nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(
        String(32), default="draft", nullable=False, index=True
    )
    is_system_seeded: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    created_by_user_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("auth_users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )


class ProblemRuleVersion(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "problem_rule_versions"
    __table_args__ = (
        UniqueConstraint(
            "problem_definition_id",
            "version",
            name="uq_problem_rule_versions_definition_version",
        ),
        Index(
            "ix_problem_rule_versions_definition_version",
            "problem_definition_id",
            "version",
        ),
        Index("ix_problem_rule_versions_system_seeded", "is_system_seeded"),
    )

    problem_definition_id: Mapped[int] = mapped_column(
        ForeignKey("problem_definitions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), default="draft", nullable=False, index=True
    )
    evaluation_grain: Mapped[str] = mapped_column(String(64), nullable=False)
    lookback_days: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    condition_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, nullable=False
    )
    impact_formula_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, nullable=False
    )
    severity_formula_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, nullable=False
    )
    confidence_formula_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, nullable=False
    )
    dedup_key_template: Mapped[str] = mapped_column(String(512), nullable=False)
    recheck_rule_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, nullable=False
    )
    evidence_template_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, nullable=False
    )
    test_only: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, index=True
    )
    seller_visible: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, index=True
    )
    visibility_mode: Mapped[str] = mapped_column(
        String(32), default="seller", nullable=False, index=True
    )
    is_system_seeded: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    created_by_user_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("auth_users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    published_by_user_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("auth_users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )


class ProblemInstance(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "problem_instances"
    __table_args__ = (
        UniqueConstraint(
            "account_id",
            "problem_code",
            "entity_type",
            "entity_id",
            "dedup_key",
            name="uq_problem_instances_account_problem_entity_dedup",
        ),
        Index("ix_problem_instances_account_status", "account_id", "status"),
        Index(
            "ix_problem_instances_account_problem_code", "account_id", "problem_code"
        ),
        Index(
            "ix_problem_instances_account_status_last_seen_id",
            "account_id",
            "status",
            "last_seen_at",
            "id",
        ),
        Index("ix_problem_instances_dedup_key", "dedup_key"),
    )

    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    problem_code: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    problem_definition_id: Mapped[int] = mapped_column(
        ForeignKey("problem_definitions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    rule_version_id: Mapped[int] = mapped_column(
        ForeignKey("problem_rule_versions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    source_module: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    entity_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    nm_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    vendor_code: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    dedup_key: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    recommendation: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(32), default="new", nullable=False, index=True
    )
    impact_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    money_impact_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    money_impact_currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    trust_state: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    confidence: Mapped[str | None] = mapped_column(String(32), nullable=True)
    evidence_ledger_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, nullable=False
    )
    calculation_snapshot_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, nullable=False
    )
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    dismissed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    dismiss_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class ProblemInstanceHistory(BigIntPKMixin, Base):
    __tablename__ = "problem_instance_history"
    __table_args__ = (
        Index(
            "ix_problem_instance_history_problem_created_id",
            "problem_instance_id",
            "created_at",
            "id",
        ),
    )

    problem_instance_id: Mapped[int] = mapped_column(
        ForeignKey("problem_instances.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    old_value_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    new_value_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    actor_user_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("auth_users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AdminRuleTestRun(BigIntPKMixin, Base):
    __tablename__ = "admin_rule_test_runs"

    rule_version_id: Mapped[int] = mapped_column(
        ForeignKey("problem_rule_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    account_id: Mapped[int | None] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    date_from: Mapped[date] = mapped_column(Date, nullable=False)
    date_to: Mapped[date] = mapped_column(Date, nullable=False)
    matched_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sample_issues_json: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, nullable=False
    )
    total_impact_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    warnings_json: Mapped[list[str]] = mapped_column(
        JSONB, default=list, nullable=False
    )
    created_by_user_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("auth_users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ProblemEvaluationRunLog(BigIntPKMixin, Base):
    __tablename__ = "problem_evaluation_run_logs"
    __table_args__ = (
        Index(
            "ix_problem_evaluation_run_logs_account_started", "account_id", "started_at"
        ),
        Index("ix_problem_evaluation_run_logs_trigger", "trigger"),
        Index("ix_problem_evaluation_run_logs_status", "status"),
    )

    account_id: Mapped[int | None] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    trigger: Mapped[str] = mapped_column(String(64), nullable=False)
    scope: Mapped[str] = mapped_column(String(64), nullable=False)
    sync_run_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("wb_sync_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    problem_instance_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("problem_instances.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    actor_user_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("auth_users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    nm_ids_json: Mapped[list[int]] = mapped_column(JSONB, default=list, nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[str] = mapped_column(String(32), default="running", nullable=False)
    rules_evaluated: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    entities_evaluated: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    issues_created: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    issues_updated: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    issues_resolved: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    issues_candidate_resolved: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    issues_skipped: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    errors_json: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    warnings_json: Mapped[list[str]] = mapped_column(
        JSONB, default=list, nullable=False
    )
    result_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ProblemRuleAdminAudit(BigIntPKMixin, Base):
    __tablename__ = "problem_rule_admin_audit"
    __table_args__ = (
        Index("ix_problem_rule_admin_audit_object", "object_type", "object_id"),
        Index("ix_problem_rule_admin_audit_event_type", "event_type"),
    )

    object_type: Mapped[str] = mapped_column(String(64), nullable=False)
    object_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    old_value_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    new_value_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    actor_user_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("auth_users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
