from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

from kb.db import make_engine, make_session_factory
from kb.db.repos import page_repo


@pytest.fixture()
def session(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("KB_DATA_DIR", str(tmp_path))
    cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.upgrade(cfg, "head")
    factory = make_session_factory(make_engine(tmp_path))
    s = factory()
    yield s
    s.close()


def test_upsert_inserts_then_updates_same_stem(session):
    row = page_repo.upsert_page(
        session,
        stem="foo",
        rel_path="concepts/foo.md",
        typed={
            "type": "concept",
            "review_status": "approved",
            "created": "2026-05-01",
            "updated": "2026-05-01",
        },
        tags=["a"],
        sources=[],
        aliases=["F"],
        extra={"k": "v"},
    )
    assert row.id > 0
    again = page_repo.upsert_page(
        session,
        stem="foo",
        rel_path="concepts/foo.md",
        typed={
            "type": "concept",
            "review_status": "approved",
            "created": "2026-05-01",
            "updated": "2026-05-02",
        },
        tags=["a", "b"],
        sources=[],
        aliases=[],
        extra={},
    )
    assert again.id == row.id  # same row, not a duplicate
    assert again.updated == "2026-05-02"
    tags = page_repo.get_tags(session, again.id)
    assert tags == ["a", "b"]
    assert page_repo.get_aliases(session, again.id) == []  # replaced, not merged


def test_get_and_delete_by_stem(session):
    page_repo.upsert_page(
        session,
        stem="bar",
        rel_path="concepts/bar.md",
        typed={
            "type": "concept",
            "review_status": "approved",
            "created": "2026-05-01",
            "updated": "2026-05-01",
        },
        tags=["t"],
        sources=[],
        aliases=[],
        extra={},
    )
    assert page_repo.get_by_stem(session, "bar") is not None
    page_repo.delete_by_stem(session, "bar")
    assert page_repo.get_by_stem(session, "bar") is None
    # cascade cleared the tag row
    assert page_repo.get_tags(session, 1) == []
