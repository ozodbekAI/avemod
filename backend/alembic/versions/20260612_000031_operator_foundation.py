"""Add universal AI operator foundation tables.

Revision ID: 20260612_000031
Revises: 20260609_000030
Create Date: 2026-06-12 16:30:00
"""

from __future__ import annotations

from alembic import op


revision = "20260612_000031"
down_revision = "20260609_000030"
branch_labels = None
depends_on = None


TABLES = (
    "operator_signals",
    "operator_diagnoses",
    "unified_actions",
    "operator_cases",
    "operator_evidence",
    "operator_drafts",
    "external_tickets",
    "result_events",
)


def _base_indexes(table: str) -> None:
    for column in ("account_id", "source_module", "nm_id", "status", "created_at"):
        op.execute(f"CREATE INDEX IF NOT EXISTS ix_{table}_{column} ON {table} ({column})")


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS operator_signals (
            id BIGSERIAL PRIMARY KEY,
            account_id BIGINT NOT NULL REFERENCES wb_accounts(id) ON DELETE CASCADE,
            source_module VARCHAR(64) NOT NULL,
            source_id VARCHAR(255) NULL,
            external_id VARCHAR(255) NULL,
            nm_id BIGINT NULL,
            vendor_code VARCHAR(255) NULL,
            signal_type VARCHAR(64) NOT NULL,
            status VARCHAR(32) NOT NULL DEFAULT 'new',
            trust_state VARCHAR(32) NOT NULL DEFAULT 'provisional',
            title VARCHAR(255) NULL,
            message TEXT NULL,
            observed_at TIMESTAMPTZ NULL,
            payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_operator_signals_source UNIQUE (account_id, source_module, source_id)
        )
        """
    )
    _base_indexes("operator_signals")
    op.execute("CREATE INDEX IF NOT EXISTS ix_operator_signals_source_id ON operator_signals (source_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_operator_signals_external_id ON operator_signals (external_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_operator_signals_vendor_code ON operator_signals (vendor_code)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_operator_signals_signal_type ON operator_signals (signal_type)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_operator_signals_trust_state ON operator_signals (trust_state)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_operator_signals_observed_at ON operator_signals (observed_at)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS operator_diagnoses (
            id BIGSERIAL PRIMARY KEY,
            account_id BIGINT NOT NULL REFERENCES wb_accounts(id) ON DELETE CASCADE,
            signal_id BIGINT NULL REFERENCES operator_signals(id) ON DELETE SET NULL,
            source_module VARCHAR(64) NOT NULL,
            source_id VARCHAR(255) NULL,
            external_id VARCHAR(255) NULL,
            nm_id BIGINT NULL,
            vendor_code VARCHAR(255) NULL,
            diagnosis_type VARCHAR(64) NOT NULL,
            status VARCHAR(32) NOT NULL DEFAULT 'new',
            trust_state VARCHAR(32) NOT NULL DEFAULT 'provisional',
            title VARCHAR(255) NULL,
            summary TEXT NULL,
            payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_operator_diagnoses_source UNIQUE (account_id, source_module, source_id)
        )
        """
    )
    _base_indexes("operator_diagnoses")
    op.execute("CREATE INDEX IF NOT EXISTS ix_operator_diagnoses_signal_id ON operator_diagnoses (signal_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_operator_diagnoses_source_id ON operator_diagnoses (source_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_operator_diagnoses_external_id ON operator_diagnoses (external_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_operator_diagnoses_vendor_code ON operator_diagnoses (vendor_code)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_operator_diagnoses_diagnosis_type ON operator_diagnoses (diagnosis_type)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_operator_diagnoses_trust_state ON operator_diagnoses (trust_state)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS unified_actions (
            id BIGSERIAL PRIMARY KEY,
            account_id BIGINT NOT NULL REFERENCES wb_accounts(id) ON DELETE CASCADE,
            diagnosis_id BIGINT NULL REFERENCES operator_diagnoses(id) ON DELETE SET NULL,
            source_module VARCHAR(64) NOT NULL,
            source_id VARCHAR(255) NULL,
            external_id VARCHAR(255) NULL,
            nm_id BIGINT NULL,
            vendor_code VARCHAR(255) NULL,
            action_type VARCHAR(64) NOT NULL,
            status VARCHAR(32) NOT NULL DEFAULT 'new',
            priority VARCHAR(8) NOT NULL DEFAULT 'P3',
            trust_state VARCHAR(32) NOT NULL DEFAULT 'provisional',
            title VARCHAR(255) NULL,
            summary TEXT NULL,
            guided_fix_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_unified_actions_source UNIQUE (account_id, source_module, source_id)
        )
        """
    )
    _base_indexes("unified_actions")
    op.execute("CREATE INDEX IF NOT EXISTS ix_unified_actions_diagnosis_id ON unified_actions (diagnosis_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_unified_actions_source_id ON unified_actions (source_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_unified_actions_external_id ON unified_actions (external_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_unified_actions_vendor_code ON unified_actions (vendor_code)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_unified_actions_action_type ON unified_actions (action_type)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_unified_actions_priority ON unified_actions (priority)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_unified_actions_trust_state ON unified_actions (trust_state)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS operator_cases (
            id BIGSERIAL PRIMARY KEY,
            account_id BIGINT NOT NULL REFERENCES wb_accounts(id) ON DELETE CASCADE,
            action_id BIGINT NULL REFERENCES unified_actions(id) ON DELETE SET NULL,
            source_module VARCHAR(64) NOT NULL,
            source_id VARCHAR(255) NULL,
            external_id VARCHAR(255) NULL,
            nm_id BIGINT NULL,
            vendor_code VARCHAR(255) NULL,
            case_type VARCHAR(64) NOT NULL,
            status VARCHAR(32) NOT NULL DEFAULT 'new',
            external_status VARCHAR(32) NOT NULL DEFAULT 'not_created',
            title VARCHAR(255) NULL,
            summary TEXT NULL,
            payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_operator_cases_source UNIQUE (account_id, source_module, source_id)
        )
        """
    )
    _base_indexes("operator_cases")
    op.execute("CREATE INDEX IF NOT EXISTS ix_operator_cases_action_id ON operator_cases (action_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_operator_cases_source_id ON operator_cases (source_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_operator_cases_external_id ON operator_cases (external_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_operator_cases_vendor_code ON operator_cases (vendor_code)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_operator_cases_case_type ON operator_cases (case_type)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_operator_cases_external_status ON operator_cases (external_status)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS operator_evidence (
            id BIGSERIAL PRIMARY KEY,
            account_id BIGINT NOT NULL REFERENCES wb_accounts(id) ON DELETE CASCADE,
            case_id BIGINT NULL REFERENCES operator_cases(id) ON DELETE CASCADE,
            source_module VARCHAR(64) NOT NULL,
            source_id VARCHAR(255) NULL,
            external_id VARCHAR(255) NULL,
            nm_id BIGINT NULL,
            vendor_code VARCHAR(255) NULL,
            evidence_type VARCHAR(64) NOT NULL,
            status VARCHAR(32) NOT NULL DEFAULT 'new',
            title VARCHAR(255) NULL,
            payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    _base_indexes("operator_evidence")
    op.execute("CREATE INDEX IF NOT EXISTS ix_operator_evidence_case_id ON operator_evidence (case_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_operator_evidence_source_id ON operator_evidence (source_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_operator_evidence_external_id ON operator_evidence (external_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_operator_evidence_vendor_code ON operator_evidence (vendor_code)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_operator_evidence_evidence_type ON operator_evidence (evidence_type)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS operator_drafts (
            id BIGSERIAL PRIMARY KEY,
            account_id BIGINT NOT NULL REFERENCES wb_accounts(id) ON DELETE CASCADE,
            action_id BIGINT NULL REFERENCES unified_actions(id) ON DELETE SET NULL,
            case_id BIGINT NULL REFERENCES operator_cases(id) ON DELETE SET NULL,
            source_module VARCHAR(64) NOT NULL,
            source_id VARCHAR(255) NULL,
            external_id VARCHAR(255) NULL,
            nm_id BIGINT NULL,
            vendor_code VARCHAR(255) NULL,
            draft_type VARCHAR(64) NOT NULL,
            status VARCHAR(32) NOT NULL DEFAULT 'new',
            external_status VARCHAR(32) NOT NULL DEFAULT 'draft_ready',
            title VARCHAR(255) NULL,
            body_text TEXT NULL,
            payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_operator_drafts_source UNIQUE (account_id, source_module, source_id)
        )
        """
    )
    _base_indexes("operator_drafts")
    op.execute("CREATE INDEX IF NOT EXISTS ix_operator_drafts_action_id ON operator_drafts (action_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_operator_drafts_case_id ON operator_drafts (case_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_operator_drafts_source_id ON operator_drafts (source_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_operator_drafts_external_id ON operator_drafts (external_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_operator_drafts_vendor_code ON operator_drafts (vendor_code)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_operator_drafts_draft_type ON operator_drafts (draft_type)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_operator_drafts_external_status ON operator_drafts (external_status)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS external_tickets (
            id BIGSERIAL PRIMARY KEY,
            account_id BIGINT NOT NULL REFERENCES wb_accounts(id) ON DELETE CASCADE,
            case_id BIGINT NULL REFERENCES operator_cases(id) ON DELETE SET NULL,
            draft_id BIGINT NULL REFERENCES operator_drafts(id) ON DELETE SET NULL,
            source_module VARCHAR(64) NOT NULL,
            source_id VARCHAR(255) NULL,
            external_id VARCHAR(255) NULL,
            nm_id BIGINT NULL,
            vendor_code VARCHAR(255) NULL,
            ticket_type VARCHAR(64) NOT NULL,
            status VARCHAR(32) NOT NULL DEFAULT 'not_created',
            title VARCHAR(255) NULL,
            payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_external_tickets_external UNIQUE (account_id, source_module, external_id)
        )
        """
    )
    _base_indexes("external_tickets")
    op.execute("CREATE INDEX IF NOT EXISTS ix_external_tickets_case_id ON external_tickets (case_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_external_tickets_draft_id ON external_tickets (draft_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_external_tickets_source_id ON external_tickets (source_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_external_tickets_external_id ON external_tickets (external_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_external_tickets_vendor_code ON external_tickets (vendor_code)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_external_tickets_ticket_type ON external_tickets (ticket_type)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS result_events (
            id BIGSERIAL PRIMARY KEY,
            account_id BIGINT NOT NULL REFERENCES wb_accounts(id) ON DELETE CASCADE,
            action_id BIGINT NULL REFERENCES unified_actions(id) ON DELETE SET NULL,
            case_id BIGINT NULL REFERENCES operator_cases(id) ON DELETE SET NULL,
            draft_id BIGINT NULL REFERENCES operator_drafts(id) ON DELETE SET NULL,
            ticket_id BIGINT NULL REFERENCES external_tickets(id) ON DELETE SET NULL,
            source_module VARCHAR(64) NOT NULL,
            source_id VARCHAR(255) NULL,
            external_id VARCHAR(255) NULL,
            nm_id BIGINT NULL,
            vendor_code VARCHAR(255) NULL,
            event_type VARCHAR(64) NOT NULL,
            status VARCHAR(32) NOT NULL DEFAULT 'new',
            external_status VARCHAR(32) NULL,
            message TEXT NULL,
            payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    _base_indexes("result_events")
    op.execute("CREATE INDEX IF NOT EXISTS ix_result_events_action_id ON result_events (action_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_result_events_case_id ON result_events (case_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_result_events_draft_id ON result_events (draft_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_result_events_ticket_id ON result_events (ticket_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_result_events_source_id ON result_events (source_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_result_events_external_id ON result_events (external_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_result_events_vendor_code ON result_events (vendor_code)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_result_events_event_type ON result_events (event_type)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_result_events_external_status ON result_events (external_status)")


def downgrade() -> None:
    for table in reversed(TABLES):
        op.execute(f"DROP TABLE IF EXISTS {table}")
