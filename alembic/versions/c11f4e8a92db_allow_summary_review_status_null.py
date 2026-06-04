"""allow summary pages without review_status

Revision ID: c11f4e8a92db
Revises: b72b13e7c9a1
Create Date: 2026-06-04 11:30:00.000000

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "c11f4e8a92db"
down_revision: Union[str, Sequence[str], None] = "b72b13e7c9a1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Allow summaries to retain their absent review_status as NULL."""
    with op.batch_alter_table("pages") as batch:
        batch.alter_column("review_status", existing_type=sa.Text(), nullable=True)


def downgrade() -> None:
    """Restore non-null page review status."""
    with op.batch_alter_table("pages") as batch:
        batch.alter_column("review_status", existing_type=sa.Text(), nullable=False)
