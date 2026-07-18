"""Add original checker semantics to local card quality issues.

Revision ID: 20260629_000045
Revises: 20260626_000044
Create Date: 2026-06-29
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260629_000045"
down_revision = "20260626_000044"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("card_quality_issues", sa.Column("suggested_value", sa.Text(), nullable=True))
    op.add_column("card_quality_issues", sa.Column("alternatives_json", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False))
    op.add_column("card_quality_issues", sa.Column("charc_id", sa.Integer(), nullable=True))
    op.add_column("card_quality_issues", sa.Column("allowed_values_json", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False))
    op.add_column("card_quality_issues", sa.Column("error_details_json", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False))
    op.add_column("card_quality_issues", sa.Column("ai_suggested_value", sa.Text(), nullable=True))
    op.add_column("card_quality_issues", sa.Column("ai_reason", sa.Text(), nullable=True))
    op.add_column("card_quality_issues", sa.Column("ai_alternatives_json", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False))
    op.add_column("card_quality_issues", sa.Column("ai_confidence", sa.Float(), nullable=True))
    op.add_column("card_quality_issues", sa.Column("requires_human_check", sa.Boolean(), server_default=sa.false(), nullable=False))
    op.add_column("card_quality_issues", sa.Column("ai_reason_short", sa.Text(), nullable=True))
    op.add_column("card_quality_issues", sa.Column("ai_reason_full", sa.Text(), nullable=True))
    op.add_column("card_quality_issues", sa.Column("ai_evidence_json", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False))
    op.add_column("card_quality_issues", sa.Column("ai_used_sources_json", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False))
    op.add_column("card_quality_issues", sa.Column("photo_evidence_json", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False))
    op.add_column("card_quality_issues", sa.Column("source", sa.String(length=50), nullable=True))
    op.add_column("card_quality_issues", sa.Column("score_impact", sa.Integer(), server_default="0", nullable=False))


def downgrade() -> None:
    op.drop_column("card_quality_issues", "score_impact")
    op.drop_column("card_quality_issues", "source")
    op.drop_column("card_quality_issues", "photo_evidence_json")
    op.drop_column("card_quality_issues", "ai_used_sources_json")
    op.drop_column("card_quality_issues", "ai_evidence_json")
    op.drop_column("card_quality_issues", "ai_reason_full")
    op.drop_column("card_quality_issues", "ai_reason_short")
    op.drop_column("card_quality_issues", "requires_human_check")
    op.drop_column("card_quality_issues", "ai_confidence")
    op.drop_column("card_quality_issues", "ai_alternatives_json")
    op.drop_column("card_quality_issues", "ai_reason")
    op.drop_column("card_quality_issues", "ai_suggested_value")
    op.drop_column("card_quality_issues", "error_details_json")
    op.drop_column("card_quality_issues", "allowed_values_json")
    op.drop_column("card_quality_issues", "charc_id")
    op.drop_column("card_quality_issues", "alternatives_json")
    op.drop_column("card_quality_issues", "suggested_value")
