"""Harden local card quality run lifecycle and snapshot integrity.

Revision ID: 20260619_000035
Revises: 20260619_000034
Create Date: 2026-06-19 01:10:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260619_000035"
down_revision = "20260619_000034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "portal_integrations",
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
    )
    op.add_column("portal_module_sync_runs", sa.Column("rows_processed", sa.Integer(), server_default="0", nullable=False))
    op.add_column("portal_module_sync_runs", sa.Column("rows_skipped", sa.Integer(), server_default="0", nullable=False))
    op.add_column("card_quality_analysis_runs", sa.Column("eligible_total", sa.Integer(), server_default="0", nullable=False))
    op.add_column("card_quality_analysis_runs", sa.Column("cards_processed", sa.Integer(), server_default="0", nullable=False))
    op.add_column("card_quality_analysis_runs", sa.Column("cards_skipped_unchanged", sa.Integer(), server_default="0", nullable=False))
    op.add_column("card_quality_analysis_runs", sa.Column("cards_failed", sa.Integer(), server_default="0", nullable=False))
    op.add_column(
        "card_quality_analysis_runs",
        sa.Column("cursor_json", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
    )
    op.add_column("card_quality_analysis_runs", sa.Column("last_processed_key", sa.String(length=128), nullable=True))
    op.add_column("card_quality_analysis_runs", sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("card_quality_analysis_runs", sa.Column("attempt", sa.Integer(), server_default="1", nullable=False))
    op.execute("UPDATE card_quality_analysis_runs SET eligible_total = cards_total WHERE eligible_total = 0")
    op.create_index(
        "ix_card_quality_analysis_runs_account_run_active",
        "card_quality_analysis_runs",
        ["account_id", "run_type", "status"],
    )
    op.create_index(
        "ix_card_quality_snapshots_current_lookup",
        "card_quality_snapshots",
        ["account_id", "nm_id", "analyzed_at"],
    )
    op.execute(
        """
        WITH ranked AS (
            SELECT
                id,
                row_number() OVER (
                    PARTITION BY account_id, nm_id, source_revision
                    ORDER BY analyzed_at DESC NULLS LAST, id DESC
                ) AS rn
            FROM card_quality_snapshots
        ),
        winners AS (
            SELECT
                duplicate.id AS duplicate_id,
                keeper.id AS keeper_id
            FROM ranked duplicate
            JOIN card_quality_snapshots duplicate_snapshot ON duplicate_snapshot.id = duplicate.id
            JOIN LATERAL (
                SELECT ranked.id
                FROM ranked
                JOIN card_quality_snapshots snapshot ON snapshot.id = ranked.id
                WHERE snapshot.account_id = duplicate_snapshot.account_id
                  AND snapshot.nm_id = duplicate_snapshot.nm_id
                  AND snapshot.source_revision = duplicate_snapshot.source_revision
                  AND ranked.rn = 1
                LIMIT 1
            ) keeper ON true
            WHERE duplicate.rn > 1
        )
        UPDATE card_quality_issues
        SET snapshot_id = winners.keeper_id
        FROM winners
        WHERE card_quality_issues.snapshot_id = winners.duplicate_id
        """
    )
    op.execute(
        """
        WITH ranked AS (
            SELECT
                id,
                row_number() OVER (
                    PARTITION BY account_id, nm_id, source_revision
                    ORDER BY analyzed_at DESC NULLS LAST, id DESC
                ) AS rn
            FROM card_quality_snapshots
        )
        DELETE FROM card_quality_snapshots
        USING ranked
        WHERE card_quality_snapshots.id = ranked.id
          AND ranked.rn > 1
        """
    )
    op.create_unique_constraint(
        "uq_card_quality_snapshots_account_nm_revision",
        "card_quality_snapshots",
        ["account_id", "nm_id", "source_revision"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_card_quality_snapshots_account_nm_revision", "card_quality_snapshots", type_="unique")
    op.drop_index("ix_card_quality_snapshots_current_lookup", table_name="card_quality_snapshots")
    op.drop_index("ix_card_quality_analysis_runs_account_run_active", table_name="card_quality_analysis_runs")
    op.drop_column("card_quality_analysis_runs", "attempt")
    op.drop_column("card_quality_analysis_runs", "heartbeat_at")
    op.drop_column("card_quality_analysis_runs", "last_processed_key")
    op.drop_column("card_quality_analysis_runs", "cursor_json")
    op.drop_column("card_quality_analysis_runs", "cards_failed")
    op.drop_column("card_quality_analysis_runs", "cards_skipped_unchanged")
    op.drop_column("card_quality_analysis_runs", "cards_processed")
    op.drop_column("card_quality_analysis_runs", "eligible_total")
    op.drop_column("portal_module_sync_runs", "rows_skipped")
    op.drop_column("portal_module_sync_runs", "rows_processed")
    op.drop_column("portal_integrations", "metadata_json")
