"""Foundation tests for the operational SQLite state DB.

Covers the initial Alembic migration round-trip, the connection-time
PRAGMAs, and the append-only triggers on ``wiki_edits``. Tasks B/C/D
build on top of this foundation.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from kb import REPO_ROOT
from kb.db import make_engine


def _alembic_cfg(data_dir: Path) -> Config:
    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "alembic"))
    return cfg


def test_alembic_round_trip(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setenv("KB_DATA_DIR", str(data_dir))

    cfg = _alembic_cfg(data_dir)

    command.upgrade(cfg, "head")

    engine = make_engine(data_dir)
    insp = inspect(engine)
    tables = set(insp.get_table_names())
    assert "dispatches" in tables
    assert "wiki_edits" in tables
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
    assert "dispatches" in tables
    assert "wiki_edits" in tables
    engine.dispose()


def test_pragmas_applied_on_connect(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setenv("KB_DATA_DIR", str(data_dir))

    cfg = _alembic_cfg(data_dir)
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


def test_wiki_edits_triggers_raise(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setenv("KB_DATA_DIR", str(data_dir))

    cfg = _alembic_cfg(data_dir)
    command.upgrade(cfg, "head")

    engine = make_engine(data_dir)
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO wiki_edits "
                "(page_stem, field, old_value, new_value, edited_at, source) "
                "VALUES (:stem, :field, :old, :new, :edited_at, :source)"
            ),
            {
                "stem": "demo-page",
                "field": "review_status",
                "old": '"not_processed"',
                "new": '"pending_for_approve"',
                "edited_at": "2026-05-26T12:00:00+09:00",
                "source": "console",
            },
        )

    with pytest.raises(IntegrityError) as update_exc:
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE wiki_edits SET page_stem = :s WHERE id = 1"),
                {"s": "other"},
            )
    assert "wiki_edits is append-only" in str(update_exc.value)

    with pytest.raises(IntegrityError) as delete_exc:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM wiki_edits WHERE id = 1"))
    assert "wiki_edits is append-only" in str(delete_exc.value)

    engine.dispose()
