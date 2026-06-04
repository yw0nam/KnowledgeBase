"""make (report_date, report_type) unique on metrics

Daily-report writers post one metrics row per (report_date, report_type).
Dedupe any existing rows (keeping the newest id per group) and replace the
non-unique index with a unique one so re-runs upsert instead of accumulating.

Revision ID: c2d3e4f5a6b7
Revises: f1a2b3c4d5e6
Create Date: 2026-06-04 22:15:00.000000

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "c2d3e4f5a6b7"
down_revision: Union[str, Sequence[str], None] = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "DELETE FROM metrics WHERE id NOT IN "
        "(SELECT MAX(id) FROM metrics GROUP BY report_date, report_type)"
    )
    op.drop_index("ix_metrics_date_type", table_name="metrics")
    op.create_index(
        "uq_metrics_date_type",
        "metrics",
        ["report_date", "report_type"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_metrics_date_type", table_name="metrics")
    op.create_index(
        "ix_metrics_date_type", "metrics", ["report_date", "report_type"]
    )
