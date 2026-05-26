"""Route tests for the Phase 2 dispatch endpoints.

Covers the three slim regression guards from spec §9.1:

- ``POST /api/dispatches/{id}/status`` requires ``Authorization: Bearer``.
- ``POST /api/dispatches/{id}/cancel`` returns 502 + leaves the row in
  ``cancelling`` when Hermes archive fails (two-state machine proof).
- ``POST /api/pages/{stem}/send-to-kanban`` inserts a ``dispatches``
  row AND leaves the page's frontmatter unchanged (Phase 1 regression
  guard for the §6.2 behavior change).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from kb import REPO_ROOT
from kb.cli.wiki_review import _kanban
from kb.db import make_engine, make_session_factory


def _alembic_cfg() -> Config:
    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "alembic"))
    return cfg


def _write_improvement_page(data_dir: Path, stem: str) -> Path:
    page_path = data_dir / "wiki" / "improvements" / "2026-05" / f"{stem}.md"
    page_path.parent.mkdir(parents=True, exist_ok=True)
    fm = {
        "type": "improvement",
        "review_status": "pending_for_approve",
        "kind": "improvement",
        "observed_at": "2026-05-26",
        "domain": "dx",
        "severity": "low",
        "issue_status": "open",
        "related": [],
        "created": "2026-05-19",
        "updated": "2026-05-19",
        "sources": ["raw/manual/x.md"],
        "tags": [],
    }
    fm_block = yaml.safe_dump(fm, sort_keys=False)
    page_path.write_text(
        f"---\n{fm_block}---\n\n# {stem} title\n\nImprovement body paragraph.\n"
    )
    return page_path


@pytest.fixture()
def data_dir(tmp_path: Path) -> Path:
    d = tmp_path / "data"
    (d / "wiki").mkdir(parents=True)
    return d


@pytest.fixture()
def client(data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("KB_DATA_DIR", str(data_dir))
    command.upgrade(_alembic_cfg(), "head")

    from kb.web.routes import kanban as kanban_route

    kanban_route._BOARDS_CACHE.clear()

    from kb.web.app import create_app

    return TestClient(create_app())


def _insert_dispatched_row(data_dir: Path, **overrides) -> int:
    """Seed a dispatched row directly via the repo so the cancel test
    has something to act on. Returns the new row id."""
    from kb.db.repos import dispatch_repo

    engine = make_engine(data_dir)
    factory = make_session_factory(engine)
    sess = factory()
    try:
        defaults = dict(
            page_stem="Foo",
            page_path_at_dispatch="wiki/improvements/2026-05/Foo.md",
            external_board_id="kb-main",
            external_task_id="t_seed",
            direction=None,
            idempotency_key=None,
            created_at="2026-05-26T10:00:00+09:00",
            dispatched_at="2026-05-26T10:00:00+09:00",
        )
        defaults.update(overrides)
        row = dispatch_repo.create_dispatch(sess, **defaults)
        return row.id
    finally:
        sess.close()
        engine.dispose()


# ---------------------------------------------------------------------------
# POST /api/dispatches/{id}/status
# ---------------------------------------------------------------------------


def test_post_status_without_bearer_returns_401(
    client: TestClient, data_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("KB_API_TOKEN", "secret-token")
    row_id = _insert_dispatched_row(data_dir)

    resp = client.post(
        f"/api/dispatches/{row_id}/status",
        json={"status": "in_progress"},
    )
    assert resp.status_code == 401, resp.text


# ---------------------------------------------------------------------------
# POST /api/dispatches/{id}/cancel
# ---------------------------------------------------------------------------


def test_post_cancel_when_hermes_archive_fails_returns_502_and_db_stays_cancelling(
    client: TestClient, data_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    row_id = _insert_dispatched_row(data_dir, external_task_id="t_to_cancel")

    def fail_archive(task_id: str) -> None:
        raise _kanban.HermesRejected("archive refused")

    monkeypatch.setattr(_kanban, "archive_card", fail_archive)

    resp = client.post(f"/api/dispatches/{row_id}/cancel")
    assert resp.status_code == 502, resp.text
    body = resp.json()
    assert body["db_state"] == "cancelling"
    assert body["detail"] == "hermes archive failed"
    assert "archive refused" in body["external_error"]

    # Re-query the DB to confirm the row is in cancelling, not cancelled.
    engine = make_engine(data_dir)
    factory = make_session_factory(engine)
    sess = factory()
    try:
        from kb.db.models import Dispatch

        row = sess.get(Dispatch, row_id)
        assert row is not None
        assert row.status == "cancelling"
    finally:
        sess.close()
        engine.dispose()


# ---------------------------------------------------------------------------
# POST /api/pages/{stem}/send-to-kanban — Phase 2 contract
# ---------------------------------------------------------------------------


def test_post_send_to_kanban_inserts_db_row_and_does_not_modify_frontmatter(
    client: TestClient, data_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    page = _write_improvement_page(data_dir, "Foo")
    original_text = page.read_text()

    monkeypatch.setattr(
        _kanban,
        "list_boards",
        lambda: [_kanban.Board(slug="kb-main", name="KB Main", counts={})],
    )
    monkeypatch.setattr(
        _kanban,
        "create_card",
        lambda **kwargs: _kanban.Card(task_id="t_db_only", board=kwargs["board_slug"]),
    )

    resp = client.post(
        "/api/pages/Foo/send-to-kanban",
        json={"board_slug": "kb-main", "direction_note": "Investigate X"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    # New §6.2 response shape.
    assert isinstance(body["id"], int)
    assert body["external_task_id"] == "t_db_only"
    assert body["external_board_id"] == "kb-main"
    assert body["dispatched_at"].endswith("+09:00")
    # Old shape keys are gone.
    assert "task_id" not in body
    assert "board_slug" not in body

    # Frontmatter MUST be unchanged: no kanban_dispatches key written.
    new_text = page.read_text()
    assert new_text == original_text
    fm = yaml.safe_load(new_text.split("---")[1])
    assert "kanban_dispatches" not in fm

    # Exactly one dispatches row exists with the expected fields.
    engine = make_engine(data_dir)
    factory = make_session_factory(engine)
    sess = factory()
    try:
        from kb.db.models import Dispatch

        rows = sess.query(Dispatch).all()
        assert len(rows) == 1
        row = rows[0]
        assert row.id == body["id"]
        assert row.page_stem == "Foo"
        assert row.external_board_id == "kb-main"
        assert row.external_task_id == "t_db_only"
        assert row.direction == "Investigate X"
        assert row.status == "dispatched"
    finally:
        sess.close()
        engine.dispose()
