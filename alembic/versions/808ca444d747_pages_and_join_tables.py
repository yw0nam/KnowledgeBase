"""pages and join tables

Revision ID: 808ca444d747
Revises: 53cdbd2e163d
Create Date: 2026-05-27 15:15:23.523301

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '808ca444d747'
down_revision: Union[str, Sequence[str], None] = '53cdbd2e163d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE pages (
            id            INTEGER PRIMARY KEY,
            stem          TEXT NOT NULL UNIQUE,
            rel_path      TEXT NOT NULL UNIQUE,
            type          TEXT NOT NULL
                          CHECK (type IN ('entity','concept','decision','question',
                                          'improvement','checklist','summary')),
            subtype       TEXT
                          CHECK (subtype IS NULL OR subtype IN ('weekly','monthly','daily')),
            category      TEXT,
            review_status TEXT
                          CHECK (review_status IS NULL OR
                                 review_status IN ('not_processed','pending_for_approve','approved')),
            period_start  TEXT CHECK (period_start IS NULL OR period_start LIKE '____-__-__%'),
            period_end    TEXT CHECK (period_end   IS NULL OR period_end   LIKE '____-__-__%'),
            created       TEXT NOT NULL,
            updated       TEXT NOT NULL,
            extra         JSON CHECK (extra IS NULL OR json_valid(extra)),
            CHECK (
              (type IN ('entity','concept','decision','improvement','checklist','question')
                 AND review_status IS NOT NULL)
              OR (type = 'summary' AND review_status IS NULL)
            )
        )
        """
    )
    op.execute("CREATE INDEX ix_pages_type_review_status ON pages(type, review_status)")
    op.execute(
        "CREATE INDEX ix_pages_review_status ON pages(review_status) "
        "WHERE review_status IS NOT NULL"
    )
    op.execute("CREATE INDEX ix_pages_type_category ON pages(type, category)")
    op.execute(
        "CREATE INDEX ix_pages_period_end ON pages(period_end DESC) WHERE type = 'summary'"
    )

    op.execute(
        """
        CREATE TABLE page_tags (
            page_id INTEGER NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
            tag     TEXT NOT NULL,
            UNIQUE(page_id, tag)
        )
        """
    )
    op.execute("CREATE INDEX ix_page_tags_tag ON page_tags(tag)")

    op.execute(
        """
        CREATE TABLE page_sources (
            page_id INTEGER NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
            source  TEXT NOT NULL,
            UNIQUE(page_id, source)
        )
        """
    )
    op.execute("CREATE INDEX ix_page_sources_source ON page_sources(source)")

    op.execute(
        """
        CREATE TABLE page_aliases (
            page_id INTEGER NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
            alias   TEXT NOT NULL,
            UNIQUE(page_id, alias)
        )
        """
    )
    op.execute("CREATE UNIQUE INDEX ux_page_aliases_alias ON page_aliases(alias)")

    # Widen wiki_edits.field + source to cover the new editable fields and the
    # CLI write source. SQLite can't ALTER a CHECK, so rebuild via the
    # 12-step table-rebuild (here: new table + copy + swap).
    op.execute(
        """
        CREATE TABLE wiki_edits_new (
            id        INTEGER PRIMARY KEY,
            page_stem TEXT NOT NULL,
            field     TEXT NOT NULL
                      CHECK (field IN ('review_status','type','category','tags',
                                       'sources','aliases','subtype',
                                       'period_start','period_end','extra')),
            old_value JSON CHECK (old_value IS NULL OR json_valid(old_value)),
            new_value JSON CHECK (new_value IS NULL OR json_valid(new_value)),
            edited_at TEXT NOT NULL
                      CHECK (edited_at LIKE '____-__-__T__:__:__+09:00'),
            source    TEXT NOT NULL DEFAULT 'console'
                      CHECK (source IN ('console','migration','cli'))
        )
        """
    )
    op.execute(
        "INSERT INTO wiki_edits_new "
        "SELECT id,page_stem,field,old_value,new_value,edited_at,source FROM wiki_edits"
    )
    op.execute("DROP TABLE wiki_edits")
    op.execute("ALTER TABLE wiki_edits_new RENAME TO wiki_edits")
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
    op.execute("DROP TABLE IF EXISTS page_aliases")
    op.execute("DROP TABLE IF EXISTS page_sources")
    op.execute("DROP TABLE IF EXISTS page_tags")
    op.execute("DROP TABLE IF EXISTS pages")
    # wiki_edits left in its widened form on downgrade — acceptable; the
    # widened CHECK is a strict superset and PR1 is the only consumer.
