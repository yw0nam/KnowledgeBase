"""Tests for ``kb.db.repos.wiki_edit_repo``.

Two behaviours that aren't covered by the route-level tests:

- ``insert_edits`` writes one row per change in a single transaction
  and returns them in input order.
- ``list_edits`` is descending by ``edited_at`` with a ``since`` cutoff
  and a capped ``limit`` (default 50, max 200), and the total count is
  unfiltered for the ``page_stem``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.orm import Session

from kb import REPO_ROOT
from kb.db import make_engine, make_session_factory


def _alembic_cfg() -> Config:
    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "alembic"))
    return cfg


@pytest.fixture()
def session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Session:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setenv("KB_DATA_DIR", str(data_dir))
    command.upgrade(_alembic_cfg(), "head")
    engine = make_engine(data_dir)
    factory = make_session_factory(engine)
    sess = factory()
    try:
        yield sess
    finally:
        sess.close()
        engine.dispose()


def test_insert_edits_writes_one_row_per_change_and_returns_them(
    session: Session,
) -> None:
    from kb.db.repos import wiki_edit_repo

    rows = wiki_edit_repo.insert_edits(
        session,
        page_stem="Foo",
        changes=[
            ("review_status", "pending_for_approve", "approved"),
            ("tags", [], ["a", "b"]),
        ],
        edited_at="2026-05-26T12:00:00+09:00",
        source="console",
    )

    assert len(rows) == 2
    assert rows[0].field == "review_status"
    assert rows[0].old_value == "pending_for_approve"
    assert rows[0].new_value == "approved"
    assert rows[1].field == "tags"
    assert rows[1].old_value == []
    assert rows[1].new_value == ["a", "b"]
    assert all(r.page_stem == "Foo" for r in rows)
    assert all(r.edited_at == "2026-05-26T12:00:00+09:00" for r in rows)
    assert all(r.source == "console" for r in rows)


def test_list_edits_descending_with_since_and_total_unfiltered(
    session: Session,
) -> None:
    from kb.db.repos import wiki_edit_repo

    wiki_edit_repo.insert_edits(
        session,
        page_stem="Foo",
        changes=[("review_status", "a", "b")],
        edited_at="2026-05-26T10:00:00+09:00",
        source="console",
    )
    wiki_edit_repo.insert_edits(
        session,
        page_stem="Foo",
        changes=[("review_status", "b", "c")],
        edited_at="2026-05-26T11:00:00+09:00",
        source="console",
    )
    wiki_edit_repo.insert_edits(
        session,
        page_stem="Foo",
        changes=[("review_status", "c", "d")],
        edited_at="2026-05-26T12:00:00+09:00",
        source="console",
    )

    rows, total = wiki_edit_repo.list_edits(
        session,
        page_stem="Foo",
        since="2026-05-26T12:00:00+09:00",
        limit=50,
    )

    # 3 rows total for Foo; since cuts off the most recent (strict `<`).
    assert total == 3
    assert [r.edited_at for r in rows] == [
        "2026-05-26T11:00:00+09:00",
        "2026-05-26T10:00:00+09:00",
    ]
