"""Add AI agent scenario engine tables.

Revision ID: 20260721_000070
Revises: 20260720_000069
Create Date: 2026-07-21 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260721_000070"
down_revision = "20260720_000069"
branch_labels = None
depends_on = None

JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        "agent_scenarios",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("account_id", sa.BigInteger(), nullable=False),
        sa.Column("created_by_user_id", sa.BigInteger(), nullable=True),
        sa.Column("updated_by_user_id", sa.BigInteger(), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "scenario_type", sa.String(length=32), server_default="general", nullable=False
        ),
        sa.Column("status", sa.String(length=32), server_default="draft", nullable=False),
        sa.Column(
            "approval_policy",
            sa.String(length=32),
            server_default="manual_review",
            nullable=False,
        ),
        sa.Column(
            "auto_execute_enabled", sa.Boolean(), server_default=sa.false(), nullable=False
        ),
        sa.Column("source_prompt", sa.Text(), nullable=True),
        sa.Column("scope_json", JSONB, server_default="{}", nullable=False),
        sa.Column("schedule_json", JSONB, server_default="{}", nullable=False),
        sa.Column("trigger_json", JSONB, server_default="{}", nullable=False),
        sa.Column("guardrails_json", JSONB, server_default="{}", nullable=False),
        sa.Column("actions_json", JSONB, server_default="[]", nullable=False),
        sa.Column("notification_json", JSONB, server_default="{}", nullable=False),
        sa.Column("ai_plan_json", JSONB, server_default="{}", nullable=False),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_run_status", sa.String(length=32), nullable=True),
        sa.ForeignKeyConstraint(["account_id"], ["wb_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["auth_users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_user_id"], ["auth_users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agent_scenarios_account_id", "agent_scenarios", ["account_id"])
    op.create_index(
        "ix_agent_scenarios_created_by_user_id",
        "agent_scenarios",
        ["created_by_user_id"],
    )
    op.create_index(
        "ix_agent_scenarios_updated_by_user_id",
        "agent_scenarios",
        ["updated_by_user_id"],
    )
    op.create_index("ix_agent_scenarios_name", "agent_scenarios", ["name"])
    op.create_index(
        "ix_agent_scenarios_scenario_type", "agent_scenarios", ["scenario_type"]
    )
    op.create_index("ix_agent_scenarios_status", "agent_scenarios", ["status"])
    op.create_index(
        "ix_agent_scenarios_approval_policy",
        "agent_scenarios",
        ["approval_policy"],
    )
    op.create_index(
        "ix_agent_scenarios_auto_execute_enabled",
        "agent_scenarios",
        ["auto_execute_enabled"],
    )
    op.create_index("ix_agent_scenarios_next_run_at", "agent_scenarios", ["next_run_at"])
    op.create_index("ix_agent_scenarios_last_run_at", "agent_scenarios", ["last_run_at"])
    op.create_index(
        "ix_agent_scenarios_last_run_status",
        "agent_scenarios",
        ["last_run_status"],
    )
    op.create_index(
        "ix_agent_scenarios_account_status",
        "agent_scenarios",
        ["account_id", "status"],
    )
    op.create_index(
        "ix_agent_scenarios_account_type",
        "agent_scenarios",
        ["account_id", "scenario_type"],
    )
    op.create_index(
        "ix_agent_scenarios_next_run",
        "agent_scenarios",
        ["status", "next_run_at"],
    )

    op.create_table(
        "agent_scenario_runs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("account_id", sa.BigInteger(), nullable=False),
        sa.Column("scenario_id", sa.BigInteger(), nullable=False),
        sa.Column("requested_by_user_id", sa.BigInteger(), nullable=True),
        sa.Column("trigger", sa.String(length=32), server_default="manual", nullable=False),
        sa.Column("status", sa.String(length=32), server_default="queued", nullable=False),
        sa.Column("dry_run", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("input_json", JSONB, server_default="{}", nullable=False),
        sa.Column("output_json", JSONB, server_default="{}", nullable=False),
        sa.Column("actions_preview_json", JSONB, server_default="[]", nullable=False),
        sa.Column("actions_executed", sa.Integer(), server_default="0", nullable=False),
        sa.Column("actions_blocked", sa.Integer(), server_default="0", nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("completion_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "estimated_cost_usd",
            sa.Numeric(18, 6),
            server_default="0",
            nullable=False,
        ),
        sa.Column("log_text", sa.Text(), nullable=True),
        sa.Column("error_code", sa.String(length=128), nullable=True),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["account_id"], ["wb_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["requested_by_user_id"], ["auth_users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["scenario_id"], ["agent_scenarios.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in (
        "account_id",
        "scenario_id",
        "requested_by_user_id",
        "trigger",
        "status",
        "started_at",
        "finished_at",
    ):
        op.create_index(
            f"ix_agent_scenario_runs_{column}", "agent_scenario_runs", [column]
        )
    op.create_index(
        "ix_agent_scenario_runs_account_created_id",
        "agent_scenario_runs",
        ["account_id", "created_at", "id"],
    )
    op.create_index(
        "ix_agent_scenario_runs_account_status",
        "agent_scenario_runs",
        ["account_id", "status"],
    )
    op.create_index(
        "ix_agent_scenario_runs_scenario_status",
        "agent_scenario_runs",
        ["scenario_id", "status"],
    )

    op.create_table(
        "agent_action_previews",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("account_id", sa.BigInteger(), nullable=False),
        sa.Column("scenario_id", sa.BigInteger(), nullable=True),
        sa.Column("run_id", sa.BigInteger(), nullable=True),
        sa.Column("api_action_key", sa.String(length=160), nullable=True),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default="pending_confirmation",
            nullable=False,
        ),
        sa.Column("confirm_required", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=240), nullable=False),
        sa.Column("before_json", JSONB, server_default="{}", nullable=False),
        sa.Column("after_json", JSONB, server_default="{}", nullable=False),
        sa.Column("payload_json", JSONB, server_default="{}", nullable=False),
        sa.Column("risk_json", JSONB, server_default="{}", nullable=False),
        sa.Column("approved_by_user_id", sa.BigInteger(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["account_id"], ["wb_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["approved_by_user_id"], ["auth_users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["run_id"], ["agent_scenario_runs.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["scenario_id"], ["agent_scenarios.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "idempotency_key", name="uq_agent_action_previews_idempotency_key"
        ),
    )
    for column in (
        "account_id",
        "scenario_id",
        "run_id",
        "api_action_key",
        "status",
        "approved_by_user_id",
        "approved_at",
    ):
        op.create_index(
            f"ix_agent_action_previews_{column}", "agent_action_previews", [column]
        )
    op.create_index(
        "ix_agent_action_previews_account_status",
        "agent_action_previews",
        ["account_id", "status"],
    )
    op.create_index(
        "ix_agent_action_previews_run_status",
        "agent_action_previews",
        ["run_id", "status"],
    )

    op.create_table(
        "agent_usage_ledger",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("account_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=True),
        sa.Column("scenario_id", sa.BigInteger(), nullable=True),
        sa.Column("run_id", sa.BigInteger(), nullable=True),
        sa.Column("provider", sa.String(length=64), server_default="openai", nullable=False),
        sa.Column("model", sa.String(length=120), nullable=True),
        sa.Column("source", sa.String(length=64), server_default="chat", nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("completion_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("total_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "estimated_cost_usd",
            sa.Numeric(18, 6),
            server_default="0",
            nullable=False,
        ),
        sa.Column("request_id", sa.String(length=255), nullable=True),
        sa.Column("payload_json", JSONB, server_default="{}", nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["wb_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["agent_scenario_runs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["scenario_id"], ["agent_scenarios.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["auth_users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("account_id", "user_id", "scenario_id", "run_id"):
        op.create_index(f"ix_agent_usage_ledger_{column}", "agent_usage_ledger", [column])
    op.create_index(
        "ix_agent_usage_ledger_account_created_id",
        "agent_usage_ledger",
        ["account_id", "created_at", "id"],
    )
    op.create_index(
        "ix_agent_usage_ledger_account_source",
        "agent_usage_ledger",
        ["account_id", "source"],
    )


def downgrade() -> None:
    op.drop_index("ix_agent_usage_ledger_account_source", table_name="agent_usage_ledger")
    op.drop_index(
        "ix_agent_usage_ledger_account_created_id", table_name="agent_usage_ledger"
    )
    for column in ("run_id", "scenario_id", "user_id", "account_id"):
        op.drop_index(f"ix_agent_usage_ledger_{column}", table_name="agent_usage_ledger")
    op.drop_table("agent_usage_ledger")

    op.drop_index(
        "ix_agent_action_previews_run_status", table_name="agent_action_previews"
    )
    op.drop_index(
        "ix_agent_action_previews_account_status", table_name="agent_action_previews"
    )
    for column in (
        "approved_at",
        "approved_by_user_id",
        "status",
        "api_action_key",
        "run_id",
        "scenario_id",
        "account_id",
    ):
        op.drop_index(
            f"ix_agent_action_previews_{column}", table_name="agent_action_previews"
        )
    op.drop_table("agent_action_previews")

    op.drop_index(
        "ix_agent_scenario_runs_scenario_status", table_name="agent_scenario_runs"
    )
    op.drop_index(
        "ix_agent_scenario_runs_account_status", table_name="agent_scenario_runs"
    )
    op.drop_index(
        "ix_agent_scenario_runs_account_created_id", table_name="agent_scenario_runs"
    )
    for column in (
        "finished_at",
        "started_at",
        "status",
        "trigger",
        "requested_by_user_id",
        "scenario_id",
        "account_id",
    ):
        op.drop_index(
            f"ix_agent_scenario_runs_{column}", table_name="agent_scenario_runs"
        )
    op.drop_table("agent_scenario_runs")

    op.drop_index("ix_agent_scenarios_next_run", table_name="agent_scenarios")
    op.drop_index("ix_agent_scenarios_account_type", table_name="agent_scenarios")
    op.drop_index("ix_agent_scenarios_account_status", table_name="agent_scenarios")
    op.drop_index("ix_agent_scenarios_last_run_status", table_name="agent_scenarios")
    op.drop_index("ix_agent_scenarios_last_run_at", table_name="agent_scenarios")
    op.drop_index("ix_agent_scenarios_next_run_at", table_name="agent_scenarios")
    op.drop_index(
        "ix_agent_scenarios_auto_execute_enabled", table_name="agent_scenarios"
    )
    op.drop_index("ix_agent_scenarios_approval_policy", table_name="agent_scenarios")
    op.drop_index("ix_agent_scenarios_status", table_name="agent_scenarios")
    op.drop_index("ix_agent_scenarios_scenario_type", table_name="agent_scenarios")
    op.drop_index("ix_agent_scenarios_name", table_name="agent_scenarios")
    op.drop_index("ix_agent_scenarios_updated_by_user_id", table_name="agent_scenarios")
    op.drop_index("ix_agent_scenarios_created_by_user_id", table_name="agent_scenarios")
    op.drop_index("ix_agent_scenarios_account_id", table_name="agent_scenarios")
    op.drop_table("agent_scenarios")
