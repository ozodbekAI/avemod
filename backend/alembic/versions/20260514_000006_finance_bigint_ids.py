"""Promote finance identifiers to bigint.

Revision ID: 20260514_000006
Revises: 20260514_000005
Create Date: 2026-05-14 18:45:00
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import context, op

# revision identifiers, used by Alembic.
revision = "20260514_000006"
down_revision = "20260514_000005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if context.is_offline_mode():
        return
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    def _alter_if_needed(table_name: str, column_name: str) -> None:
        columns = {column["name"]: column for column in inspector.get_columns(table_name)}
        column = columns.get(column_name)
        if column is None:
            return
        if isinstance(column["type"], sa.BigInteger):
            return
        op.alter_column(table_name, column_name, existing_type=sa.INTEGER(), type_=sa.BigInteger())

    _alter_if_needed("wb_realization_reports", "report_id")
    _alter_if_needed("wb_realization_report_rows", "rrd_id")
    _alter_if_needed("wb_realization_report_rows", "order_id")
    _alter_if_needed("wb_realization_report_rows", "shk_id")
    _alter_if_needed("wb_realization_report_rows", "report_id")
    _alter_if_needed("wb_acquiring_reports", "report_id")
    _alter_if_needed("wb_acquiring_report_rows", "report_id")
    _alter_if_needed("wb_acquiring_report_rows", "order_id")
    _alter_if_needed("wb_acquiring_report_rows", "shk_id")


def downgrade() -> None:
    op.alter_column("wb_acquiring_report_rows", "shk_id", existing_type=sa.BigInteger(), type_=sa.INTEGER())
    op.alter_column("wb_acquiring_report_rows", "order_id", existing_type=sa.BigInteger(), type_=sa.INTEGER())
    op.alter_column("wb_acquiring_report_rows", "report_id", existing_type=sa.BigInteger(), type_=sa.INTEGER())
    op.alter_column("wb_acquiring_reports", "report_id", existing_type=sa.BigInteger(), type_=sa.INTEGER())
    op.alter_column("wb_realization_report_rows", "report_id", existing_type=sa.BigInteger(), type_=sa.INTEGER())
    op.alter_column("wb_realization_report_rows", "shk_id", existing_type=sa.BigInteger(), type_=sa.INTEGER())
    op.alter_column("wb_realization_report_rows", "order_id", existing_type=sa.BigInteger(), type_=sa.INTEGER())
    op.alter_column("wb_realization_report_rows", "rrd_id", existing_type=sa.BigInteger(), type_=sa.INTEGER())
    op.alter_column("wb_realization_reports", "report_id", existing_type=sa.BigInteger(), type_=sa.INTEGER())
