"""Foundation tests for the operational SQLite state DB.

Covers the initial Alembic migration round-trip, the connection-time
PRAGMAs, and the append-only triggers. Tasks B/C/D
build on top of this foundation.
"""

from __future__ import annotations

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from kb import REPO_ROOT
from kb.db import make_engine


def _alembic_cfg() -> Config:
    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "alembic"))
    return cfg


def test_alembic_round_trip(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setenv("KB_DATA_DIR", str(data_dir))

    cfg = _alembic_cfg()

    command.upgrade(cfg, "head")

    engine = make_engine(data_dir)
    insp = inspect(engine)
    tables = set(insp.get_table_names())
    assert {
        "dispatches",
        "page_revisions",
        "page_sources",
        "pages",
        "raw_sources",
        "wiki_edits",
    }.issubset(tables)
    engine.dispose()

    command.downgrade(cfg, "base")
    engine = make_engine(data_dir)
    insp = inspect(engine)
    tables = set(insp.get_table_names())
    assert "dispatches" not in tables
    assert "wiki_edits" not in tables
    engine.dispose()

    command.upgrade(cfg, "head")
    engine = make_engine(data_dir)
    insp = inspect(engine)
    tables = set(insp.get_table_names())
    assert {
        "dispatches",
        "page_revisions",
        "page_sources",
        "pages",
        "raw_sources",
        "wiki_edits",
    }.issubset(tables)
    engine.dispose()


def test_canonical_append_only_triggers_raise(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setenv("KB_DATA_DIR", str(data_dir))

    cfg = _alembic_cfg()
    command.upgrade(cfg, "head")

    engine = make_engine(data_dir)
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO raw_sources "
                "(source_key, source_type, content_md, frontmatter, created_at) "
                "VALUES (:key, :type, :content, :frontmatter, :created_at)"
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
                "VALUES (:slug, :title, :type, :status, :body, :frontmatter, "
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
                "VALUES (1, 1, :kind, :body, :frontmatter, :created_at, :source)"
            ),
            {
                "kind": "import",
                "body": "page body",
                "frontmatter": "{}",
                "created_at": "2026-06-04T10:32:00+09:00",
                "source": "migration",
            },
        )

    with pytest.raises(IntegrityError) as raw_update_exc:
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE raw_sources SET content_md = :body WHERE id = 1"),
                {"body": "changed"},
            )
    assert "raw_sources is append-only" in str(raw_update_exc.value)

    with pytest.raises(IntegrityError) as raw_delete_exc:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM raw_sources WHERE id = 1"))
    assert "raw_sources is append-only" in str(raw_delete_exc.value)

    with pytest.raises(IntegrityError) as revision_update_exc:
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE page_revisions SET note = :note WHERE id = 1"),
                {"note": "changed"},
            )
    assert "page_revisions is append-only" in str(revision_update_exc.value)

    with pytest.raises(IntegrityError) as revision_delete_exc:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM page_revisions WHERE id = 1"))
    assert "page_revisions is append-only" in str(revision_delete_exc.value)

    engine.dispose()


def test_pragmas_applied_on_connect(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setenv("KB_DATA_DIR", str(data_dir))

    cfg = _alembic_cfg()
    command.upgrade(cfg, "head")

    engine = make_engine(data_dir)
    with engine.connect() as conn:
        journal_mode = conn.execute(text("PRAGMA journal_mode")).scalar()
        foreign_keys = conn.execute(text("PRAGMA foreign_keys")).scalar()
        busy_timeout = conn.execute(text("PRAGMA busy_timeout")).scalar()
        synchronous = conn.execute(text("PRAGMA synchronous")).scalar()
    engine.dispose()

    assert journal_mode == "wal"
    assert foreign_keys == 1
    assert busy_timeout == 5000
    assert synchronous == 1
