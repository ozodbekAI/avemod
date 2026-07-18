"""Add explicit user to account access grants.

Revision ID: 20260609_000030
Revises: 20260609_000029
Create Date: 2026-06-09 16:00:00
"""

from __future__ import annotations

from alembic import op


revision = "20260609_000030"
down_revision = "20260609_000029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS auth_user_account_access (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL REFERENCES auth_users(id) ON DELETE CASCADE,
            account_id BIGINT NOT NULL REFERENCES wb_accounts(id) ON DELETE CASCADE,
            role VARCHAR(32) NOT NULL DEFAULT 'viewer',
            is_default BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_auth_user_account_access_user_account UNIQUE (user_id, account_id)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_auth_user_account_access_user_id ON auth_user_account_access (user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_auth_user_account_access_account_id ON auth_user_account_access (account_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS auth_user_account_access")
