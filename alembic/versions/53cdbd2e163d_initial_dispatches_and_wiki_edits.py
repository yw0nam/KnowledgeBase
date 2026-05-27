"""initial dispatches and wiki_edits

Revision ID: 53cdbd2e163d
Revises:
Create Date: 2026-05-26 15:51:00.423650

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "53cdbd2e163d"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create ``dispatches`` and ``wiki_edits`` with the spec DDL."""
    op.execute(
        """
        CREATE TABLE dispatches (
            id              INTEGER PRIMARY KEY,
            page_stem       TEXT NOT NULL,
            page_path_at_dispatch TEXT NOT NULL,
            external_board_id  TEXT NOT NULL,
            external_task_id   TEXT NOT NULL,
            direction       TEXT,
            status          TEXT NOT NULL DEFAULT 'dispatched'
                            CHECK (status IN ('dispatched','in_progress','done','failed','cancelled','cancelling')),
            idempotency_key TEXT,
            created_at      TEXT NOT NULL
                            CHECK (created_at      LIKE '____-__-__T__:__:__+09:00'),
            dispatched_at   TEXT NOT NULL
                            CHECK (dispatched_at   LIKE '____-__-__T__:__:__+09:00'),
            last_status_at  TEXT
                            CHECK (last_status_at IS NULL OR last_status_at LIKE '____-__-__T__:__:__+09:00'),
            result_payload  JSON
                            CHECK (result_payload IS NULL OR json_valid(result_payload)),
            UNIQUE (external_board_id, external_task_id)
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX ux_dispatches_idempotency_key "
        "ON dispatches(idempotency_key) WHERE idempotency_key IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX ix_dispatches_status_dispatched_at "
        "ON dispatches(status, dispatched_at DESC)"
    )
    op.execute(
        "CREATE INDEX ix_dispatches_page_stem_dispatched_at "
        "ON dispatches(page_stem, dispatched_at DESC)"
    )

    op.execute(
        """
        CREATE TABLE wiki_edits (
            id              INTEGER PRIMARY KEY,
            page_stem       TEXT NOT NULL,
            field           TEXT NOT NULL
                            CHECK (field IN ('review_status','type','category','tags')),
            old_value       JSON CHECK (old_value IS NULL OR json_valid(old_value)),
            new_value       JSON CHECK (new_value IS NULL OR json_valid(new_value)),
            edited_at       TEXT NOT NULL
                            CHECK (edited_at LIKE '____-__-__T__:__:__+09:00'),
            source          TEXT NOT NULL DEFAULT 'console'
                            CHECK (source IN ('console','migration'))
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_wiki_edits_page_stem_edited_at "
        "ON wiki_edits(page_stem, edited_at DESC)"
    )
    op.execute(
        "CREATE INDEX ix_wiki_edits_review_status_transitions "
        "ON wiki_edits(edited_at) WHERE field = 'review_status'"
    )
    op.execute(
        """
        CREATE TRIGGER trg_wiki_edits_no_update
        BEFORE UPDATE ON wiki_edits
        BEGIN SELECT RAISE(ABORT, 'wiki_edits is append-only'); END
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_wiki_edits_no_delete
        BEFORE DELETE ON wiki_edits
        BEGIN SELECT RAISE(ABORT, 'wiki_edits is append-only'); END
        """
    )


def downgrade() -> None:
    """Drop both tables (triggers and indexes go with them)."""
    op.execute("DROP TABLE IF EXISTS wiki_edits")
    op.execute("DROP TABLE IF EXISTS dispatches")
