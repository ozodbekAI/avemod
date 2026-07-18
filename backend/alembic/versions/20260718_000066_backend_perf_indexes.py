"""Add hot-path backend performance indexes.

Revision ID: 20260718_000066
Revises: 20260712_000065
Create Date: 2026-07-18
"""

from __future__ import annotations

from alembic import op


revision = "20260718_000066"
down_revision = "20260712_000065"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_action_recommendations_account_window
        ON action_recommendations (account_id, source_date_from, source_date_to)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_action_recommendations_account_window_status
        ON action_recommendations (account_id, source_date_from, source_date_to, status)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_action_recommendations_account_status_sku
        ON action_recommendations (account_id, status, sku_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_api_snapshots_lookup_ready
        ON api_response_snapshots (namespace, endpoint_key, account_id, params_hash, snapshot_status)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_api_snapshots_refresh_due
        ON api_response_snapshots (
            namespace,
            account_id,
            snapshot_status,
            expires_at,
            access_count,
            last_accessed_at
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_api_snapshots_refresh_due")
    op.execute("DROP INDEX IF EXISTS ix_api_snapshots_lookup_ready")
    op.execute("DROP INDEX IF EXISTS ix_action_recommendations_account_status_sku")
    op.execute("DROP INDEX IF EXISTS ix_action_recommendations_account_window_status")
    op.execute("DROP INDEX IF EXISTS ix_action_recommendations_account_window")
