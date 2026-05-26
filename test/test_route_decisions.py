"""Backend route tests for the Decisions browser (spec §6.4).

Two endpoint families covered here:

- ``PATCH /api/pages/{stem}/frontmatter`` — the audit-coupled write
  pipeline. Tests assert lint integration, atomic file rename, DB
  audit insertion, type-change rejection, and the "file written but
  DB commit failed" recovery contract.
- ``GET  /api/decisions``, ``/api/enums/categories``,
  ``/api/pages/{stem}/edits``, ``/api/pages/{stem}/timeline`` — lock
  the read contracts (filters compose, dispatch summary, distinct
  categories, edit/dispatch UNION).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from kb import REPO_ROOT
from kb.db import make_engine, make_session_factory


def _alembic_cfg() -> Config:
    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "alembic"))
    return cfg


def _write_page(
    data_dir: Path,
    rel: str,
    fm: dict,
    body: str = "Body paragraph for the page.\n",
) -> Path:
    """Write a wiki page with the given relative path and frontmatter."""
    path = data_dir / "wiki" / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    fm_block = yaml.safe_dump(fm, sort_keys=False, allow_unicode=True)
    path.write_text(f"---\n{fm_block}---\n\n# {path.stem}\n\n{body}")
    return path


def _entity_fm(**over) -> dict:
    fm = {
        "type": "entity",
        "review_status": "pending_for_approve",
        "created": "2026-05-26",
        "updated": "2026-05-26",
        "sources": [],
        "tags": [],
    }
    fm.update(over)
    return fm


def _improvement_fm(**over) -> dict:
    fm = {
        "type": "improvement",
        "review_status": "pending_for_approve",
        "kind": "improvement",
        "observed_at": "2026-05-26",
        "domain": "dx",
        "severity": "low",
        "issue_status": "open",
        "related": [],
        "created": "2026-05-26",
        "updated": "2026-05-26",
        "sources": [],
        "tags": [],
    }
    fm.update(over)
    return fm


@pytest.fixture()
def data_dir(tmp_path: Path) -> Path:
    d = tmp_path / "data"
    (d / "wiki").mkdir(parents=True)
    (d / "raw").mkdir(parents=True)
    return d


@pytest.fixture()
def client(data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("KB_DATA_DIR", str(data_dir))
    command.upgrade(_alembic_cfg(), "head")
    from kb.web.app import create_app

    return TestClient(create_app())


def _read_fm(path: Path) -> dict:
    text = path.read_text()
    return yaml.safe_load(text.split("---", 2)[1])


# ---------------------------------------------------------------------------
# PATCH /api/pages/{stem}/frontmatter — spec §9.1 (4 tests)
# ---------------------------------------------------------------------------


def test_patch_frontmatter_single_field_atomic_rename_and_edit_row_inserted(
    client: TestClient, data_dir: Path
) -> None:
    """Happy path: PATCH review_status → file updated + one wiki_edits row."""
    page = _write_page(
        data_dir,
        "entities/Foo/2026-05/Foo-page.md",
        _entity_fm(review_status="pending_for_approve"),
    )
    # Subject hub + inbound link so the file doesn't trip the orphan
    # warning (lint check_index_sync needs it listed).
    _write_page(
        data_dir,
        "entities/Foo/_index.md",
        {
            "type": "index",
            "created": "2026-05-26",
            "updated": "2026-05-26",
        },
        body="## Pages\n\n- [[Foo-page]]\n",
    )

    resp = client.patch(
        "/api/pages/Foo-page/frontmatter",
        json={"review_status": "approved"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["stem"] == "Foo-page"
    assert body["frontmatter"]["review_status"] == "approved"
    assert len(body["edits"]) == 1
    assert body["edits"][0]["field"] == "review_status"

    # File on disk reflects the new value.
    assert _read_fm(page)["review_status"] == "approved"

    # Exactly one wiki_edits row with the expected diff payload.
    engine = make_engine(data_dir)
    factory = make_session_factory(engine)
    sess = factory()
    try:
        from kb.db.models import WikiEdit

        rows = sess.query(WikiEdit).all()
        assert len(rows) == 1
        assert rows[0].page_stem == "Foo-page"
        assert rows[0].field == "review_status"
        assert rows[0].old_value == "pending_for_approve"
        assert rows[0].new_value == "approved"
    finally:
        sess.close()
        engine.dispose()


def test_patch_frontmatter_lint_failure_returns_409_and_file_unchanged(
    client: TestClient, data_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Lint failure on the candidate → 409 + file untouched + no audit row.

    The candidate is linted against the corpus before any write or DB
    insert. We monkeypatch ``lint`` to append a synthetic error so the
    test stays decoupled from a specific lint check.
    """
    page = _write_page(
        data_dir,
        "entities/Foo/2026-05/Foo-page.md",
        _entity_fm(review_status="pending_for_approve"),
    )
    _write_page(
        data_dir,
        "entities/Foo/_index.md",
        {
            "type": "index",
            "created": "2026-05-26",
            "updated": "2026-05-26",
        },
        body="## Pages\n\n- [[Foo-page]]\n",
    )
    original = page.read_text()

    from kb.web.routes import pages as pages_route

    def failing_lint(result, **kwargs):  # noqa: ARG001
        result.error("entities/Foo/2026-05/Foo-page.md", "synthetic lint failure")

    monkeypatch.setattr(pages_route, "lint", failing_lint)

    resp = client.patch(
        "/api/pages/Foo-page/frontmatter",
        json={"review_status": "approved"},
    )
    assert resp.status_code == 409, resp.text
    body = resp.json()
    assert body["detail"] == "lint failed"
    assert any("synthetic lint failure" in line for line in body["lint_errors"])

    # File is untouched.
    assert page.read_text() == original

    # No wiki_edits row.
    engine = make_engine(data_dir)
    factory = make_session_factory(engine)
    sess = factory()
    try:
        from kb.db.models import WikiEdit

        assert sess.query(WikiEdit).count() == 0
    finally:
        sess.close()
        engine.dispose()


def test_patch_type_change_requiring_rename_returns_409(
    client: TestClient, data_dir: Path
) -> None:
    """``type`` change that crosses directories must reject before writing."""
    page = _write_page(
        data_dir,
        "entities/Foo/2026-05/Foo-page.md",
        _entity_fm(),
    )
    _write_page(
        data_dir,
        "entities/Foo/_index.md",
        {
            "type": "index",
            "created": "2026-05-26",
            "updated": "2026-05-26",
        },
        body="## Pages\n\n- [[Foo-page]]\n",
    )
    original = page.read_text()

    resp = client.patch(
        "/api/pages/Foo-page/frontmatter",
        json={"type": "concept"},
    )
    assert resp.status_code == 409, resp.text
    assert resp.json()["detail"] == "type change requires manual rename"

    # File untouched.
    assert page.read_text() == original

    # No wiki_edits row.
    engine = make_engine(data_dir)
    factory = make_session_factory(engine)
    sess = factory()
    try:
        from kb.db.models import WikiEdit

        assert sess.query(WikiEdit).count() == 0
    finally:
        sess.close()
        engine.dispose()


def test_patch_frontmatter_db_commit_fails_returns_500_and_retry_returns_200_with_no_edits(
    client: TestClient, data_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Recovery contract (spec §6.4 step 8).

    File replace succeeds but the wiki_edits INSERT fails. Surface 500
    with ``file_written: true``. A retry from the client reads the now-
    updated file, computes an empty diff, and returns 200 with
    ``edits: []`` — the audit gap remains.
    """
    page = _write_page(
        data_dir,
        "entities/Foo/2026-05/Foo-page.md",
        _entity_fm(review_status="pending_for_approve"),
    )
    _write_page(
        data_dir,
        "entities/Foo/_index.md",
        {
            "type": "index",
            "created": "2026-05-26",
            "updated": "2026-05-26",
        },
        body="## Pages\n\n- [[Foo-page]]\n",
    )

    from kb.db.repos import wiki_edit_repo
    from kb.web.routes import pages as pages_route

    def failing_insert(*args, **kwargs):
        raise RuntimeError("simulated DB failure")

    monkeypatch.setattr(pages_route.wiki_edit_repo, "insert_edits", failing_insert)

    resp = client.patch(
        "/api/pages/Foo-page/frontmatter",
        json={"review_status": "approved"},
    )
    assert resp.status_code == 500, resp.text
    body = resp.json()
    assert body["detail"] == "frontmatter written, audit failed"
    assert body["file_written"] is True

    # File IS updated even though DB insert failed (proves the
    # ordering — atomic rename runs before insert).
    assert _read_fm(page)["review_status"] == "approved"

    # Restore the real repo for the retry.
    monkeypatch.setattr(
        pages_route.wiki_edit_repo, "insert_edits", wiki_edit_repo.insert_edits
    )

    # Retry: file already reflects target state → diff empty → 200, no edits.
    resp2 = client.patch(
        "/api/pages/Foo-page/frontmatter",
        json={"review_status": "approved"},
    )
    assert resp2.status_code == 200, resp2.text
    assert resp2.json()["edits"] == []

    # No wiki_edits row was ever inserted (audit gap, as documented).
    engine = make_engine(data_dir)
    factory = make_session_factory(engine)
    sess = factory()
    try:
        from kb.db.models import WikiEdit

        assert sess.query(WikiEdit).count() == 0
    finally:
        sess.close()
        engine.dispose()


# ---------------------------------------------------------------------------
# Decision-browser reads (4 tests, spec §6.4)
# ---------------------------------------------------------------------------


def test_get_decisions_filters_combine_correctly(
    client: TestClient, data_dir: Path
) -> None:
    """status + type filters compose as AND, multi-value filters as OR."""
    _write_page(
        data_dir,
        "entities/Foo/2026-05/A.md",
        _entity_fm(review_status="approved", category="system-ops"),
    )
    _write_page(
        data_dir,
        "concepts/B.md",
        {
            "type": "concept",
            "review_status": "approved",
            "category": "process",
            "created": "2026-05-26",
            "updated": "2026-05-26",
            "sources": [],
            "tags": [],
        },
    )
    _write_page(
        data_dir,
        "entities/Foo/2026-05/C.md",
        _entity_fm(review_status="pending_for_approve"),
    )

    # status=approved → A + B
    resp = client.get("/api/decisions", params={"status": "approved"})
    assert resp.status_code == 200, resp.text
    stems = sorted(it["stem"] for it in resp.json()["items"])
    assert stems == ["A", "B"]

    # status=approved + type=entity → only A
    resp = client.get(
        "/api/decisions", params=[("status", "approved"), ("type", "entity")]
    )
    stems = [it["stem"] for it in resp.json()["items"]]
    assert stems == ["A"]


def test_get_decisions_dispatch_summary_count_and_last_status(
    client: TestClient, data_dir: Path
) -> None:
    """Dispatch summary aggregates count + latest status per stem."""
    _write_page(
        data_dir,
        "improvements/2026-05/Disp.md",
        _improvement_fm(review_status="approved"),
    )

    from kb.db.repos import dispatch_repo

    engine = make_engine(data_dir)
    factory = make_session_factory(engine)
    sess = factory()
    try:
        d1 = dispatch_repo.create_dispatch(
            sess,
            page_stem="Disp",
            page_path_at_dispatch="wiki/improvements/2026-05/Disp.md",
            external_board_id="kb-main",
            external_task_id="t1",
            direction=None,
            idempotency_key=None,
            created_at="2026-05-26T09:00:00+09:00",
            dispatched_at="2026-05-26T09:00:00+09:00",
        )
        dispatch_repo.create_dispatch(
            sess,
            page_stem="Disp",
            page_path_at_dispatch="wiki/improvements/2026-05/Disp.md",
            external_board_id="kb-main",
            external_task_id="t2",
            direction=None,
            idempotency_key=None,
            created_at="2026-05-26T10:00:00+09:00",
            dispatched_at="2026-05-26T10:00:00+09:00",
        )
        # Push t1 to 'done' AFTER t2 was dispatched → t1's last_status_at
        # wins, so summary.last_status == 'done'.
        dispatch_repo.update_status(
            sess,
            dispatch_id=d1.id,
            new_status="done",
            occurred_at=None,
            result_payload=None,
            server_now="2026-05-26T11:00:00+09:00",
        )
    finally:
        sess.close()
        engine.dispose()

    resp = client.get("/api/decisions", params={"status": "approved"})
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    row = next(it for it in items if it["stem"] == "Disp")
    assert row["dispatch_summary"]["count"] == 2
    assert row["dispatch_summary"]["last_status"] == "done"


def test_get_enums_categories_distinct_values(
    client: TestClient, data_dir: Path
) -> None:
    """Distinct categories under the requested type, sorted alphabetically."""
    _write_page(
        data_dir,
        "entities/Foo/2026-05/A.md",
        _entity_fm(category="system-ops"),
    )
    _write_page(
        data_dir,
        "entities/Foo/2026-05/B.md",
        _entity_fm(category="tooling"),
    )
    # Duplicate value should dedupe.
    _write_page(
        data_dir,
        "entities/Foo/2026-05/C.md",
        _entity_fm(category="system-ops"),
    )
    # Page without category — must not appear.
    _write_page(
        data_dir,
        "entities/Foo/2026-05/D.md",
        _entity_fm(),
    )

    resp = client.get("/api/enums/categories", params={"type": "entity"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["categories"] == ["system-ops", "tooling"]


def test_get_timeline_unions_edits_and_dispatches(
    client: TestClient, data_dir: Path
) -> None:
    """Timeline returns wiki_edits + dispatch events for one page, desc."""
    _write_page(
        data_dir,
        "improvements/2026-05/Tline.md",
        _improvement_fm(),
    )

    from kb.db.repos import dispatch_repo, wiki_edit_repo

    engine = make_engine(data_dir)
    factory = make_session_factory(engine)
    sess = factory()
    try:
        wiki_edit_repo.insert_edits(
            sess,
            page_stem="Tline",
            changes=[("review_status", "pending_for_approve", "approved")],
            edited_at="2026-05-26T11:00:00+09:00",
            source="console",
        )
        dispatch_repo.create_dispatch(
            sess,
            page_stem="Tline",
            page_path_at_dispatch="wiki/improvements/2026-05/Tline.md",
            external_board_id="kb-main",
            external_task_id="t_tline",
            direction=None,
            idempotency_key=None,
            created_at="2026-05-26T10:00:00+09:00",
            dispatched_at="2026-05-26T10:00:00+09:00",
        )
    finally:
        sess.close()
        engine.dispose()

    resp = client.get("/api/pages/Tline/timeline")
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    assert len(items) == 2
    # Descending by timestamp.
    assert items[0]["kind"] == "edit"
    assert items[0]["at"] == "2026-05-26T11:00:00+09:00"
    assert items[1]["kind"] == "dispatched"
    assert items[1]["at"] == "2026-05-26T10:00:00+09:00"
