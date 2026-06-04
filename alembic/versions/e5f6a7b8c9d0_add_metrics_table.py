"""add metrics table

Revision ID: e5f6a7b8c9d0
Revises: d45ea2f6b7a0
Create Date: 2026-06-04 21:30:00.000000

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, Sequence[str], None] = "d45ea2f6b7a0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "metrics",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("report_date", sa.Text(), nullable=False),
        sa.Column("report_type", sa.Text(), nullable=False),
        sa.Column("session_count", sa.Integer(), nullable=True),
        sa.Column("token_total", sa.Integer(), nullable=True),
        sa.Column("cost_usd", sa.Float(), nullable=True),
        sa.Column("tool_error_count", sa.Integer(), nullable=True),
        sa.Column("metrics_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
    )
    op.create_index(
        "ix_metrics_date_type", "metrics", ["report_date", "report_type"]
    )


def downgrade() -> None:
    op.drop_table("metrics")
