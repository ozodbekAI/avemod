"""Rebuild marketing dedupe keys with the current application formula.

Revision ID: 20260516_000018
Revises: 20260516_000017
Create Date: 2026-05-16 02:05:00
"""

from __future__ import annotations

from alembic import op


revision = "20260516_000018"
down_revision = "20260516_000017"
branch_labels = None
depends_on = None


def _deduplicate_by_dedupe_key(table_name: str) -> None:
    op.execute(
        f"""
        DELETE FROM {table_name}
        WHERE id IN (
            SELECT id
            FROM (
                SELECT
                    id,
                    row_number() OVER (
                        PARTITION BY dedupe_key
                        ORDER BY id DESC
                    ) AS rn
                FROM {table_name}
                WHERE dedupe_key IS NOT NULL
            ) ranked
            WHERE ranked.rn > 1
        )
        """
    )


def upgrade() -> None:
    op.execute(
        """
        UPDATE wb_ad_stats_daily
        SET dedupe_key = encode(
            digest(
                concat_ws(
                    '|',
                    COALESCE(account_id::text, '<null>'),
                    COALESCE(advert_id::text, '<null>'),
                    COALESCE(to_char(stat_date, 'YYYY-MM-DD'), '<null>'),
                    COALESCE(nm_id::text, '<null>')
                ),
                'sha256'
            ),
            'hex'
        )
        """
    )
    op.execute(
        """
        UPDATE wb_ad_cluster_stats
        SET dedupe_key = encode(
            digest(
                concat_ws(
                    '|',
                    COALESCE(account_id::text, '<null>'),
                    COALESCE(advert_id::text, '<null>'),
                    COALESCE(to_char(stat_date, 'YYYY-MM-DD'), '<null>'),
                    COALESCE(cluster, '<null>'),
                    COALESCE(nm_id::text, '<null>')
                ),
                'sha256'
            ),
            'hex'
        )
        """
    )
    op.execute(
        """
        UPDATE wb_region_sales_daily
        SET dedupe_key = encode(
            digest(
                concat_ws(
                    '|',
                    COALESCE(account_id::text, '<null>'),
                    COALESCE(to_char(stat_date, 'YYYY-MM-DD'), '<null>'),
                    COALESCE(country_name, '<null>'),
                    COALESCE(region_name, '<null>'),
                    COALESCE(city_name, '<null>'),
                    COALESCE(nm_id::text, '<null>'),
                    COALESCE(vendor_code, '<null>')
                ),
                'sha256'
            ),
            'hex'
        )
        """
    )
    _deduplicate_by_dedupe_key("wb_ad_stats_daily")
    _deduplicate_by_dedupe_key("wb_ad_cluster_stats")
    _deduplicate_by_dedupe_key("wb_region_sales_daily")


def downgrade() -> None:
    raise NotImplementedError("Downgrades are intentionally not supported.")
