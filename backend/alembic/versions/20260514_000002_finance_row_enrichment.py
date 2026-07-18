"""Enrich finance detail rows.

Revision ID: 20260514_000002
Revises: 20260514_000001
Create Date: 2026-05-14 17:05:00
"""
from __future__ import annotations

from alembic import context, op
import sqlalchemy as sa


revision = "20260514_000002"
down_revision = "20260514_000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if context.is_offline_mode():
        return
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    rr_columns = {column["name"] for column in inspector.get_columns("wb_realization_report_rows")}
    rr_indexes = {index["name"] for index in inspector.get_indexes("wb_realization_report_rows")}
    acquiring_columns = {column["name"] for column in inspector.get_columns("wb_acquiring_report_rows")}
    acquiring_indexes = {index["name"] for index in inspector.get_indexes("wb_acquiring_report_rows")}

    if "report_id" not in rr_columns:
        op.add_column("wb_realization_report_rows", sa.Column("report_id", sa.BigInteger(), nullable=True))
    if "doc_type_name" not in rr_columns:
        op.add_column("wb_realization_report_rows", sa.Column("doc_type_name", sa.String(length=255), nullable=True))
    if "quantity" not in rr_columns:
        op.add_column("wb_realization_report_rows", sa.Column("quantity", sa.Integer(), nullable=True))
    if "ix_wb_realization_report_rows_report_id" not in rr_indexes:
        op.create_index(
            "ix_wb_realization_report_rows_report_id",
            "wb_realization_report_rows",
            ["report_id"],
            unique=False,
        )

    if "report_id" not in acquiring_columns:
        op.add_column("wb_acquiring_report_rows", sa.Column("report_id", sa.BigInteger(), nullable=True))
    if "ix_wb_acquiring_report_rows_report_id" not in acquiring_indexes:
        op.create_index(
            "ix_wb_acquiring_report_rows_report_id",
            "wb_acquiring_report_rows",
            ["report_id"],
            unique=False,
        )


def downgrade() -> None:
    op.drop_index("ix_wb_acquiring_report_rows_report_id", table_name="wb_acquiring_report_rows")
    op.drop_column("wb_acquiring_report_rows", "report_id")

    op.drop_index("ix_wb_realization_report_rows_report_id", table_name="wb_realization_report_rows")
    op.drop_column("wb_realization_report_rows", "quantity")
    op.drop_column("wb_realization_report_rows", "doc_type_name")
    op.drop_column("wb_realization_report_rows", "report_id")
