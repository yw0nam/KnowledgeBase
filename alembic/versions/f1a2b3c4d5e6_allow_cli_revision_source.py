"""allow 'cli' as a page_revisions.source value

Deterministic CLI jobs (the daily-report writers) record their page revisions
with source='cli'. Widen the named ``ck_page_revisions_source`` CHECK.

Revision ID: f1a2b3c4d5e6
Revises: e5f6a7b8c9d0
Create Date: 2026-06-04 22:00:00.000000

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, Sequence[str], None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop whichever name exists: fresh DBs name it ck_page_revisions_source
    # (b72b), pre-existing DBs carry the auto-named page_revisions_source_check.
    op.execute(
        "ALTER TABLE page_revisions DROP CONSTRAINT IF EXISTS ck_page_revisions_source"
    )
    op.execute(
        "ALTER TABLE page_revisions DROP CONSTRAINT IF EXISTS page_revisions_source_check"
    )
    op.execute(
        "ALTER TABLE page_revisions ADD CONSTRAINT ck_page_revisions_source "
        "CHECK (source IN ('migration','console','agent','system','cli'))"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE page_revisions DROP CONSTRAINT IF EXISTS ck_page_revisions_source"
    )
    op.execute(
        "ALTER TABLE page_revisions ADD CONSTRAINT ck_page_revisions_source "
        "CHECK (source IN ('migration','console','agent','system'))"
    )
