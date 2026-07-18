"""Link result events to Dynamic Problem instances.

Revision ID: 20260707_000062
Revises: 20260706_000061
Create Date: 2026-07-07
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260707_000062"
down_revision = "20260706_000061"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("result_events", sa.Column("problem_instance_id", sa.BigInteger(), nullable=True))
    op.add_column("result_events", sa.Column("problem_code", sa.String(length=128), nullable=True))
    op.create_foreign_key(
        "fk_result_events_problem_instance_id_problem_instances",
        "result_events",
        "problem_instances",
        ["problem_instance_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_result_events_problem_instance_id", "result_events", ["problem_instance_id"])
    op.create_index("ix_result_events_problem_code", "result_events", ["problem_code"])
    op.create_index(
        "ix_result_events_account_problem_instance",
        "result_events",
        ["account_id", "problem_instance_id"],
    )
    op.create_index(
        "ix_result_events_account_problem_code",
        "result_events",
        ["account_id", "problem_code"],
    )


def downgrade() -> None:
    op.drop_index("ix_result_events_account_problem_code", table_name="result_events")
    op.drop_index("ix_result_events_account_problem_instance", table_name="result_events")
    op.drop_index("ix_result_events_problem_code", table_name="result_events")
    op.drop_index("ix_result_events_problem_instance_id", table_name="result_events")
    op.drop_constraint(
        "fk_result_events_problem_instance_id_problem_instances",
        "result_events",
        type_="foreignkey",
    )
    op.drop_column("result_events", "problem_code")
    op.drop_column("result_events", "problem_instance_id")
