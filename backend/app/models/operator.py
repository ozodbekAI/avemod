from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    event,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, BigIntPKMixin, TimestampMixin


SECRET_FIELD_TOKENS = (
    "api_key",
    "authorization",
    "credential",
    "encrypted_token",
    "encryption_key",
    "headers",
    "jwt",
    "password",
    "refresh_token",
    "secret",
    "token",
)


def scrub_operator_payload(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: scrub_operator_payload(item)
            for key, item in value.items()
            if not any(token in str(key).lower() for token in SECRET_FIELD_TOKENS)
        }
    if isinstance(value, list):
        return [scrub_operator_payload(item) for item in value]
    return value


class OperatorSignal(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "operator_signals"
    __table_args__ = (
        UniqueConstraint(
            "account_id",
            "source_module",
            "source_id",
            name="uq_operator_signals_source",
        ),
        Index("ix_operator_signals_created_at", "created_at"),
    )

    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE"), index=True
    )
    source_module: Mapped[str] = mapped_column(String(64), index=True)
    source_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    external_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    nm_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    vendor_code: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    signal_type: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(
        String(32), default="new", nullable=False, index=True
    )
    trust_state: Mapped[str] = mapped_column(
        String(32), default="provisional", nullable=False, index=True
    )
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    observed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    payload_json: Mapped[dict] = mapped_column(JSONB, default=dict)


class OperatorDiagnosis(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "operator_diagnoses"
    __table_args__ = (
        UniqueConstraint(
            "account_id",
            "source_module",
            "source_id",
            name="uq_operator_diagnoses_source",
        ),
        Index("ix_operator_diagnoses_created_at", "created_at"),
    )

    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE"), index=True
    )
    signal_id: Mapped[int | None] = mapped_column(
        ForeignKey("operator_signals.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    source_module: Mapped[str] = mapped_column(String(64), index=True)
    source_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    external_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    nm_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    vendor_code: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    diagnosis_type: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(
        String(32), default="new", nullable=False, index=True
    )
    trust_state: Mapped[str] = mapped_column(
        String(32), default="provisional", nullable=False, index=True
    )
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload_json: Mapped[dict] = mapped_column(JSONB, default=dict)


class UnifiedAction(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "unified_actions"
    __table_args__ = (
        UniqueConstraint(
            "account_id", "source_module", "source_id", name="uq_unified_actions_source"
        ),
        Index("ix_unified_actions_created_at", "created_at"),
        Index(
            "ix_unified_actions_account_created_id", "account_id", "created_at", "id"
        ),
    )

    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE"), index=True
    )
    diagnosis_id: Mapped[int | None] = mapped_column(
        ForeignKey("operator_diagnoses.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    source_module: Mapped[str] = mapped_column(String(64), index=True)
    source_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    external_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    nm_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    vendor_code: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    action_type: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(
        String(32), default="new", nullable=False, index=True
    )
    priority: Mapped[str] = mapped_column(
        String(8), default="P3", nullable=False, index=True
    )
    trust_state: Mapped[str] = mapped_column(
        String(32), default="provisional", nullable=False, index=True
    )
    assigned_to_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("auth_users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    deadline_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    review_status: Mapped[str] = mapped_column(
        String(32), default="new", nullable=False, index=True
    )
    last_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    dismissed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    guided_fix_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    payload_json: Mapped[dict] = mapped_column(JSONB, default=dict)


class ManualTaskItem(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "manual_task_items"
    __table_args__ = (
        UniqueConstraint(
            "action_id", "item_key", name="uq_manual_task_items_action_item_key"
        ),
        Index("ix_manual_task_items_account_status", "account_id", "status"),
        Index("ix_manual_task_items_action_status", "action_id", "status"),
        Index("ix_manual_task_items_nm_status", "nm_id", "status"),
    )

    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE"), index=True
    )
    action_id: Mapped[int] = mapped_column(
        ForeignKey("unified_actions.id", ondelete="CASCADE"), index=True
    )
    item_key: Mapped[str] = mapped_column(String(64), nullable=False)
    nm_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    sku_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    vendor_code: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    photo_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), default="pending", nullable=False, index=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    completed_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("auth_users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    skipped_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    skipped_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("auth_users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    last_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    product_json: Mapped[dict] = mapped_column(JSONB, default=dict)


class OperatorCase(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "operator_cases"
    __table_args__ = (
        UniqueConstraint(
            "account_id", "source_module", "source_id", name="uq_operator_cases_source"
        ),
        Index("ix_operator_cases_created_at", "created_at"),
    )

    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE"), index=True
    )
    action_id: Mapped[int | None] = mapped_column(
        ForeignKey("unified_actions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    source_module: Mapped[str] = mapped_column(String(64), index=True)
    source_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    external_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    nm_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    vendor_code: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    case_type: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(
        String(32), default="new", nullable=False, index=True
    )
    external_status: Mapped[str] = mapped_column(
        String(32), default="not_created", nullable=False, index=True
    )
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload_json: Mapped[dict] = mapped_column(JSONB, default=dict)


class OperatorEvidence(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "operator_evidence"
    __table_args__ = (Index("ix_operator_evidence_created_at", "created_at"),)

    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE"), index=True
    )
    case_id: Mapped[int | None] = mapped_column(
        ForeignKey("operator_cases.id", ondelete="CASCADE"), nullable=True, index=True
    )
    source_module: Mapped[str] = mapped_column(String(64), index=True)
    source_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    external_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    nm_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    vendor_code: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    evidence_type: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(
        String(32), default="new", nullable=False, index=True
    )
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    payload_json: Mapped[dict] = mapped_column(JSONB, default=dict)


class OperatorDraft(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "operator_drafts"
    __table_args__ = (
        UniqueConstraint(
            "account_id", "source_module", "source_id", name="uq_operator_drafts_source"
        ),
        Index("ix_operator_drafts_created_at", "created_at"),
    )

    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE"), index=True
    )
    action_id: Mapped[int | None] = mapped_column(
        ForeignKey("unified_actions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    case_id: Mapped[int | None] = mapped_column(
        ForeignKey("operator_cases.id", ondelete="SET NULL"), nullable=True, index=True
    )
    source_module: Mapped[str] = mapped_column(String(64), index=True)
    source_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    external_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    nm_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    vendor_code: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    draft_type: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(
        String(32), default="new", nullable=False, index=True
    )
    external_status: Mapped[str] = mapped_column(
        String(32), default="draft_ready", nullable=False, index=True
    )
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    body_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload_json: Mapped[dict] = mapped_column(JSONB, default=dict)


class ExternalTicket(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "external_tickets"
    __table_args__ = (
        UniqueConstraint(
            "account_id",
            "source_module",
            "external_id",
            name="uq_external_tickets_external",
        ),
        Index("ix_external_tickets_created_at", "created_at"),
    )

    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE"), index=True
    )
    case_id: Mapped[int | None] = mapped_column(
        ForeignKey("operator_cases.id", ondelete="SET NULL"), nullable=True, index=True
    )
    draft_id: Mapped[int | None] = mapped_column(
        ForeignKey("operator_drafts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    source_module: Mapped[str] = mapped_column(String(64), index=True)
    source_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    external_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    nm_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    vendor_code: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    ticket_type: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(
        String(32), default="not_created", nullable=False, index=True
    )
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    payload_json: Mapped[dict] = mapped_column(JSONB, default=dict)


class ResultEvent(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "result_events"
    __table_args__ = (
        Index("ix_result_events_created_at", "created_at"),
        Index(
            "ix_result_events_account_problem_instance",
            "account_id",
            "problem_instance_id",
        ),
        Index("ix_result_events_account_problem_code", "account_id", "problem_code"),
    )

    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE"), index=True
    )
    action_id: Mapped[int | None] = mapped_column(
        ForeignKey("unified_actions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    case_id: Mapped[int | None] = mapped_column(
        ForeignKey("operator_cases.id", ondelete="SET NULL"), nullable=True, index=True
    )
    draft_id: Mapped[int | None] = mapped_column(
        ForeignKey("operator_drafts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    ticket_id: Mapped[int | None] = mapped_column(
        ForeignKey("external_tickets.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    problem_instance_id: Mapped[int | None] = mapped_column(
        ForeignKey("problem_instances.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    problem_code: Mapped[str | None] = mapped_column(
        String(128), nullable=True, index=True
    )
    source_module: Mapped[str] = mapped_column(String(64), index=True)
    source_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    external_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    nm_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    vendor_code: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(
        String(32), default="new", nullable=False, index=True
    )
    external_status: Mapped[str | None] = mapped_column(
        String(32), nullable=True, index=True
    )
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload_json: Mapped[dict] = mapped_column(JSONB, default=dict)


class PortalIntegration(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "portal_integrations"
    __table_args__ = (
        UniqueConstraint(
            "account_id", "module", name="uq_portal_integrations_account_module"
        ),
        Index("ix_portal_integrations_account_module", "account_id", "module"),
        Index("ix_portal_integrations_status", "status"),
    )

    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE"), index=True
    )
    module: Mapped[str] = mapped_column(String(64), index=True)
    enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, index=True
    )
    mode: Mapped[str] = mapped_column(
        String(32), default="local", nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(
        String(32), default="not_configured", nullable=False, index=True
    )
    configuration_encrypted_json: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    last_sync_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    last_success_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    last_error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    last_error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class PortalModuleSyncRun(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "portal_module_sync_runs"
    __table_args__ = (
        Index(
            "ix_portal_module_sync_runs_account_module_started",
            "account_id",
            "module",
            "started_at",
        ),
        Index("ix_portal_module_sync_runs_status", "status"),
    )

    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE"), index=True
    )
    module: Mapped[str] = mapped_column(String(64), index=True)
    run_type: Mapped[str] = mapped_column(
        String(64), default="sync", nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(
        String(32), default="queued", nullable=False, index=True
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    rows_received: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rows_processed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rows_created: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rows_updated: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rows_skipped: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rows_failed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)


OPERATOR_PAYLOAD_MODELS = (
    OperatorSignal,
    OperatorDiagnosis,
    UnifiedAction,
    OperatorCase,
    OperatorEvidence,
    OperatorDraft,
    ExternalTicket,
    ResultEvent,
)


def _scrub_operator_model_payloads(mapper, connection, target) -> None:
    for attr_name in ("payload_json", "guided_fix_json"):
        if hasattr(target, attr_name):
            setattr(
                target,
                attr_name,
                scrub_operator_payload(getattr(target, attr_name) or {}),
            )


for _model in OPERATOR_PAYLOAD_MODELS:
    event.listen(_model, "before_insert", _scrub_operator_model_payloads)
    event.listen(_model, "before_update", _scrub_operator_model_payloads)
