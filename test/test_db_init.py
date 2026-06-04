"""Foundation tests for the Postgres state DB.

Covers the Alembic migration round-trip and the append-only triggers
(``RAISE EXCEPTION '<table> is append-only'``).
"""

from __future__ import annotations

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text
from sqlalchemy.exc import DBAPIError

from kb import REPO_ROOT
from kb.db import make_engine

CANONICAL_TABLES = {
    "dispatches",
    "page_revisions",
    "page_sources",
    "pages",
    "raw_sources",
    "wiki_edits",
}


def _alembic_cfg() -> Config:
    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "alembic"))
    return cfg


def test_alembic_round_trip(database_url):
    cfg = _alembic_cfg()  # reads DATABASE_URL (the per-test clone) via env

    engine = make_engine()
    assert CANONICAL_TABLES.issubset(set(inspect(engine).get_table_names()))
    engine.dispose()

    command.downgrade(cfg, "base")
    engine = make_engine()
    tables = set(inspect(engine).get_table_names())
    assert "dispatches" not in tables
    assert "wiki_edits" not in tables
    engine.dispose()

    command.upgrade(cfg, "head")
    engine = make_engine()
    assert CANONICAL_TABLES.issubset(set(inspect(engine).get_table_names()))
    engine.dispose()


def test_canonical_append_only_triggers_raise(database_url):
    engine = make_engine()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO raw_sources "
                "(source_key, source_type, content_md, frontmatter, created_at) "
                "VALUES (:key, :type, :content, (:frontmatter)::jsonb, :created_at)"
            ),
            {
                "key": "raw/manual/demo.md",
                "type": "manual",
                "content": "source body",
                "frontmatter": "{}",
                "created_at": "2026-06-04T10:30:00+09:00",
            },
        )
        conn.execute(
            text(
                "INSERT INTO pages "
                "(slug, title, type, review_status, body_md, frontmatter, "
                "created_at, updated_at) "
                "VALUES (:slug, :title, :type, :status, :body, (:frontmatter)::jsonb, "
                ":created_at, :updated_at)"
            ),
            {
                "slug": "demo-page",
                "title": "Demo Page",
                "type": "decision",
                "status": "pending_for_approve",
                "body": "page body",
                "frontmatter": "{}",
                "created_at": "2026-06-04T10:31:00+09:00",
                "updated_at": "2026-06-04T10:31:00+09:00",
            },
        )
        conn.execute(
            text(
                "INSERT INTO page_revisions "
                "(page_id, revision_number, change_kind, body_md, frontmatter, "
                "created_at, source) "
                "VALUES (1, 1, :kind, :body, (:frontmatter)::jsonb, :created_at, :source)"
            ),
            {
                "kind": "import",
                "body": "page body",
                "frontmatter": "{}",
                "created_at": "2026-06-04T10:32:00+09:00",
                "source": "migration",
            },
        )

    with pytest.raises(DBAPIError) as raw_update_exc:
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE raw_sources SET content_md = :body WHERE id = 1"),
                {"body": "changed"},
            )
    assert "raw_sources is append-only" in str(raw_update_exc.value)

    with pytest.raises(DBAPIError) as raw_delete_exc:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM raw_sources WHERE id = 1"))
    assert "raw_sources is append-only" in str(raw_delete_exc.value)

    with pytest.raises(DBAPIError) as revision_update_exc:
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE page_revisions SET note = :note WHERE id = 1"),
                {"note": "changed"},
            )
    assert "page_revisions is append-only" in str(revision_update_exc.value)

    with pytest.raises(DBAPIError) as revision_delete_exc:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM page_revisions WHERE id = 1"))
    assert "page_revisions is append-only" in str(revision_delete_exc.value)

    engine.dispose()
