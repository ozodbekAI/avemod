"""Add minimal portal experiment/change events.

Revision ID: 20260609_000029
Revises: 20260606_000028
Create Date: 2026-06-09 12:00:00
"""

from __future__ import annotations

from alembic import op


revision = "20260609_000029"
down_revision = "20260606_000028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS experiment_events (
            id BIGSERIAL PRIMARY KEY,
            account_id BIGINT NOT NULL REFERENCES wb_accounts(id) ON DELETE CASCADE,
            nm_id BIGINT NOT NULL,
            sku_id BIGINT NULL REFERENCES core_sku(id) ON DELETE SET NULL,
            action_id BIGINT NULL REFERENCES action_recommendations(id) ON DELETE SET NULL,
            event_type VARCHAR(64) NOT NULL,
            before_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            after_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            changed_at TIMESTAMPTZ NOT NULL,
            created_by BIGINT NULL REFERENCES auth_users(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_experiment_events_account_id ON experiment_events (account_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_experiment_events_nm_id ON experiment_events (nm_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_experiment_events_sku_id ON experiment_events (sku_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_experiment_events_action_id ON experiment_events (action_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_experiment_events_event_type ON experiment_events (event_type)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_experiment_events_changed_at ON experiment_events (changed_at)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_experiment_events_created_by ON experiment_events (created_by)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS experiment_events")
