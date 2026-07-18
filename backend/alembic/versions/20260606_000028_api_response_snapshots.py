"""Persist API response snapshots for heavy money endpoints.

Revision ID: 20260606_000028
Revises: 20260603_000027
Create Date: 2026-06-06 14:30:00
"""

from __future__ import annotations

from alembic import op


revision = "20260606_000028"
down_revision = "20260603_000027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS api_response_snapshots (
            id BIGSERIAL PRIMARY KEY,
            namespace VARCHAR(64) NOT NULL,
            endpoint_key VARCHAR(128) NOT NULL,
            account_id BIGINT NOT NULL REFERENCES wb_accounts(id) ON DELETE CASCADE,
            date_from DATE NULL,
            date_to DATE NULL,
            params_hash VARCHAR(64) NOT NULL,
            request_params JSONB NOT NULL DEFAULT '{}'::jsonb,
            response_model VARCHAR(128) NOT NULL DEFAULT '',
            payload JSONB NOT NULL DEFAULT '{}'::jsonb,
            snapshot_status VARCHAR(32) NOT NULL DEFAULT 'ready',
            last_error TEXT NULL,
            computed_at TIMESTAMPTZ NOT NULL,
            expires_at TIMESTAMPTZ NULL,
            last_accessed_at TIMESTAMPTZ NULL,
            access_count INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_api_response_snapshots_namespace_endpoint_account_params
                UNIQUE (namespace, endpoint_key, account_id, params_hash)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_api_response_snapshots_namespace
        ON api_response_snapshots (namespace)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_api_response_snapshots_endpoint_key
        ON api_response_snapshots (endpoint_key)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_api_response_snapshots_account_id
        ON api_response_snapshots (account_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_api_response_snapshots_date_from
        ON api_response_snapshots (date_from)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_api_response_snapshots_date_to
        ON api_response_snapshots (date_to)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_api_response_snapshots_params_hash
        ON api_response_snapshots (params_hash)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_api_response_snapshots_snapshot_status
        ON api_response_snapshots (snapshot_status)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_api_response_snapshots_expires_at
        ON api_response_snapshots (expires_at)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_api_response_snapshots_last_accessed_at
        ON api_response_snapshots (last_accessed_at)
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS api_response_snapshots")
