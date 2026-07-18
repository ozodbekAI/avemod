"""Add WB Promotion Calendar tables.

Revision ID: 20260718_000068
Revises: 20260718_000067
Create Date: 2026-07-18
"""

from __future__ import annotations

from alembic import op


revision = "20260718_000068"
down_revision = "20260718_000067"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS wb_promotion_calendar (
            id BIGSERIAL PRIMARY KEY,
            account_id BIGINT NOT NULL REFERENCES wb_accounts(id) ON DELETE CASCADE,
            promotion_id BIGINT NOT NULL,
            name VARCHAR(500),
            promo_type VARCHAR(64),
            start_at TIMESTAMPTZ,
            end_at TIMESTAMPTZ,
            description TEXT,
            advantages JSONB,
            in_promo_action_leftovers INTEGER,
            in_promo_action_total INTEGER,
            not_in_promo_action_leftovers INTEGER,
            not_in_promo_action_total INTEGER,
            participation_percentage INTEGER,
            exception_products_count INTEGER,
            snapshot_at TIMESTAMPTZ NOT NULL,
            payload JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_wb_promotion_calendar_account_id UNIQUE (account_id, promotion_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_wb_promotion_calendar_promotion_id ON wb_promotion_calendar (promotion_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_wb_promotion_calendar_start_at ON wb_promotion_calendar (start_at)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_wb_promotion_calendar_end_at ON wb_promotion_calendar (end_at)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS wb_promotion_nomenclatures (
            id BIGSERIAL PRIMARY KEY,
            account_id BIGINT NOT NULL REFERENCES wb_accounts(id) ON DELETE CASCADE,
            promotion_id BIGINT NOT NULL,
            nm_id BIGINT NOT NULL,
            in_action BOOLEAN NOT NULL DEFAULT false,
            price NUMERIC(18, 4),
            currency_code VARCHAR(8),
            plan_price NUMERIC(18, 4),
            discount INTEGER,
            plan_discount INTEGER,
            snapshot_at TIMESTAMPTZ NOT NULL,
            payload JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_wb_promotion_nomenclatures_account_id UNIQUE (account_id, promotion_id, nm_id, in_action)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_wb_promotion_nomenclatures_promotion_id ON wb_promotion_nomenclatures (promotion_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_wb_promotion_nomenclatures_nm_id ON wb_promotion_nomenclatures (nm_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_wb_promotion_nomenclatures_in_action ON wb_promotion_nomenclatures (in_action)"
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_wb_promotion_nomenclatures_account_nm_action
        ON wb_promotion_nomenclatures (account_id, nm_id, in_action)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_wb_promotion_nomenclatures_account_nm_action")
    op.execute("DROP TABLE IF EXISTS wb_promotion_nomenclatures")
    op.execute("DROP TABLE IF EXISTS wb_promotion_calendar")
