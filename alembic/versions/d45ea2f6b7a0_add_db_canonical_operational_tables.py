"""add db canonical operational tables

Revision ID: d45ea2f6b7a0
Revises: c11f4e8a92db
Create Date: 2026-06-04 12:15:00.000000

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "d45ea2f6b7a0"
down_revision: Union[str, Sequence[str], None] = "c11f4e8a92db"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "handoffs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("handoff_id", sa.Text(), nullable=False, unique=True),
        sa.Column("task_slug", sa.Text(), nullable=False),
        sa.Column("subject", sa.Text(), nullable=True),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("handoff_seq", sa.Integer(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("frontmatter", sa.JSON(), nullable=False),
        sa.Column("body_md", sa.Text(), nullable=False),
        sa.Column("export_path", sa.Text(), nullable=False, unique=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
    )
    op.create_index("ix_handoffs_task_status", "handoffs", ["task_slug", "status"])

    op.create_table(
        "operation_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("log_date", sa.Text(), nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("body_md", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
    )
    op.create_index(
        "ix_operation_logs_log_date", "operation_logs", ["log_date", "id"]
    )

    op.create_table(
        "cron_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("job_name", sa.Text(), nullable=False),
        sa.Column("target", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("exit_code", sa.Integer(), nullable=True),
        sa.Column("log_body", sa.Text(), nullable=False),
        sa.Column("log_path", sa.Text(), nullable=True),
        sa.Column("started_at", sa.Text(), nullable=True),
        sa.Column("finished_at", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
    )
    op.create_index("ix_cron_runs_target_job", "cron_runs", ["target", "job_name"])

    op.create_table(
        "exports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("target", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("exported_at", sa.Text(), nullable=False),
    )
    op.create_index("ix_exports_exported_at", "exports", ["exported_at"])


def downgrade() -> None:
    op.drop_table("exports")
    op.drop_table("cron_runs")
    op.drop_table("operation_logs")
    op.drop_table("handoffs")
