from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
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


class AgentScenario(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "agent_scenarios"
    __table_args__ = (
        Index("ix_agent_scenarios_account_status", "account_id", "status"),
        Index("ix_agent_scenarios_account_type", "account_id", "scenario_type"),
        Index("ix_agent_scenarios_next_run", "status", "next_run_at"),
    )

    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE"), index=True
    )
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("auth_users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    updated_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("auth_users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(200), index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    scenario_type: Mapped[str] = mapped_column(
        String(32), default="general", nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(
        String(32), default="draft", nullable=False, index=True
    )
    approval_policy: Mapped[str] = mapped_column(
        String(32), default="manual_review", nullable=False, index=True
    )
    auto_execute_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, index=True
    )
    source_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    scope_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    schedule_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    trigger_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    guardrails_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    actions_json: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    notification_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    ai_plan_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    next_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    last_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    last_run_status: Mapped[str | None] = mapped_column(
        String(32), nullable=True, index=True
    )


class AgentScenarioRun(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "agent_scenario_runs"
    __table_args__ = (
        Index(
            "ix_agent_scenario_runs_account_created_id",
            "account_id",
            "created_at",
            "id",
        ),
        Index("ix_agent_scenario_runs_account_status", "account_id", "status"),
        Index("ix_agent_scenario_runs_scenario_status", "scenario_id", "status"),
    )

    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE"), index=True
    )
    scenario_id: Mapped[int] = mapped_column(
        ForeignKey("agent_scenarios.id", ondelete="CASCADE"), index=True
    )
    requested_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("auth_users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    trigger: Mapped[str] = mapped_column(
        String(32), default="manual", nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(
        String(32), default="queued", nullable=False, index=True
    )
    dry_run: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    input_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    output_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    actions_preview_json: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list
    )
    actions_executed: Mapped[int] = mapped_column(default=0, nullable=False)
    actions_blocked: Mapped[int] = mapped_column(default=0, nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(default=0, nullable=False)
    completion_tokens: Mapped[int] = mapped_column(default=0, nullable=False)
    estimated_cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), default=Decimal("0"), nullable=False
    )
    log_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)


class AgentActionPreview(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "agent_action_previews"
    __table_args__ = (
        UniqueConstraint(
            "idempotency_key", name="uq_agent_action_previews_idempotency_key"
        ),
        Index("ix_agent_action_previews_account_status", "account_id", "status"),
        Index("ix_agent_action_previews_run_status", "run_id", "status"),
    )

    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE"), index=True
    )
    scenario_id: Mapped[int | None] = mapped_column(
        ForeignKey("agent_scenarios.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    run_id: Mapped[int | None] = mapped_column(
        ForeignKey("agent_scenario_runs.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    api_action_key: Mapped[str | None] = mapped_column(
        String(160), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(240))
    status: Mapped[str] = mapped_column(
        String(32), default="pending_confirmation", nullable=False, index=True
    )
    confirm_required: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
    idempotency_key: Mapped[str] = mapped_column(String(240))
    before_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    after_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    risk_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    approved_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("auth_users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )


class AgentUsageLedger(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "agent_usage_ledger"
    __table_args__ = (
        Index(
            "ix_agent_usage_ledger_account_created_id",
            "account_id",
            "created_at",
            "id",
        ),
        Index("ix_agent_usage_ledger_account_source", "account_id", "source"),
    )

    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("auth_users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    scenario_id: Mapped[int | None] = mapped_column(
        ForeignKey("agent_scenarios.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    run_id: Mapped[int | None] = mapped_column(
        ForeignKey("agent_scenario_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    provider: Mapped[str] = mapped_column(String(64), default="openai", nullable=False)
    model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    source: Mapped[str] = mapped_column(String(64), default="chat", nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(default=0, nullable=False)
    completion_tokens: Mapped[int] = mapped_column(default=0, nullable=False)
    total_tokens: Mapped[int] = mapped_column(default=0, nullable=False)
    estimated_cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), default=Decimal("0"), nullable=False
    )
    request_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
