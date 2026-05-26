"""Route tests for kanban dispatch endpoints.

Covers GET /api/kanban/boards (success, cache hit, 503) and
POST /api/pages/{stem}/send-to-kanban (success, 404, 409, 400, 503,
rollback success path, rollback-failure body shape).

Helpers in ``_kanban`` are monkeypatched so no real subprocess runs.
The page fixture mirrors the spec's improvement-page shape.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from kb_mcp.cli.wiki_review import _kanban

# ---------------------------------------------------------------------------
# Corpus + client fixtures
# ---------------------------------------------------------------------------


def _write_improvement_page(
    data_dir: Path,
    stem: str,
    status: str = "pending_for_approve",
    extra_fm: dict | None = None,
) -> Path:
    """Write a minimal pending improvement page under wiki/improvements/."""
    page_path = data_dir / "wiki" / "improvements" / "2026-05" / f"{stem}.md"
    page_path.parent.mkdir(parents=True, exist_ok=True)
    fm = {
        "type": "improvement",
        "review_status": status,
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
    if extra_fm:
        fm.update(extra_fm)
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
    # Always start with an empty boards cache so cache-hit tests are
    # deterministic across the whole module.
    from kb_mcp.web.routes import kanban as kanban_route

    kanban_route._BOARDS_CACHE.clear()

    from kb_mcp.web.app import create_app

    return TestClient(create_app())


def _patch_list_boards(monkeypatch: pytest.MonkeyPatch, boards):
    """Replace ``_kanban.list_boards`` and count its invocations."""
    state = {"calls": 0}

    def fake(*args, **kwargs):
        state["calls"] += 1
        if callable(boards):
            return boards()
        return list(boards)

    monkeypatch.setattr(_kanban, "list_boards", fake)
    return state


# ---------------------------------------------------------------------------
# GET /api/kanban/boards
# ---------------------------------------------------------------------------


def test_get_boards_success(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_list_boards(
        monkeypatch,
        [
            _kanban.Board(slug="kb-main", name="KB Main", counts={"ready": 3}),
            _kanban.Board(slug="kb-spike", name="KB Spike", counts={}),
        ],
    )
    resp = client.get("/api/kanban/boards")
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert payload == {
        "boards": [
            {"slug": "kb-main", "name": "KB Main", "counts": {"ready": 3}},
            {"slug": "kb-spike", "name": "KB Spike", "counts": {}},
        ]
    }


def test_get_boards_uses_cache_on_second_call(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = _patch_list_boards(
        monkeypatch,
        [_kanban.Board(slug="kb-main", name="KB Main", counts={})],
    )
    client.get("/api/kanban/boards")
    client.get("/api/kanban/boards")
    assert state["calls"] == 1


def test_get_boards_503_on_hermes_unavailable(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom():
        raise _kanban.HermesUnavailable("daemon down")

    monkeypatch.setattr(_kanban, "list_boards", boom)
    resp = client.get("/api/kanban/boards")
    assert resp.status_code == 503
    assert "Hermes" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# POST /api/pages/{stem}/send-to-kanban
# ---------------------------------------------------------------------------


def test_send_to_kanban_success_writes_frontmatter(
    client: TestClient, data_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    page = _write_improvement_page(data_dir, "Foo")
    _patch_list_boards(
        monkeypatch,
        [_kanban.Board(slug="kb-main", name="KB Main", counts={})],
    )

    created_bodies: list[str] = []

    def fake_create(board_slug, title, body):
        created_bodies.append(body)
        return _kanban.Card(task_id="t_abc", board=board_slug)

    monkeypatch.setattr(_kanban, "create_card", fake_create)

    resp = client.post(
        "/api/pages/Foo/send-to-kanban",
        json={"board_slug": "kb-main", "direction_note": "Investigate X"},
    )
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert payload["task_id"] == "t_abc"
    assert payload["board_slug"] == "kb-main"
    assert "dispatched_at" in payload
    assert payload["dispatched_at"].endswith("+09:00")

    # Frontmatter updated with the dispatch entry.
    fm = yaml.safe_load(page.read_text().split("---")[1])
    assert fm["kanban_dispatches"][-1]["task_id"] == "t_abc"
    assert fm["kanban_dispatches"][-1]["board"] == "kb-main"
    assert fm["kanban_dispatches"][-1]["direction"] == "Investigate X"

    # Card body carries the kb-meta fallback line.
    assert created_bodies, "create_card was not invoked"
    assert "<!-- kb-meta:" in created_bodies[0]
    assert '"kb_page_stem":"Foo"' in created_bodies[0]


def test_send_to_kanban_404_when_page_missing(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_list_boards(
        monkeypatch, [_kanban.Board(slug="kb-main", name="KB Main", counts={})]
    )
    resp = client.post(
        "/api/pages/NoSuchPage/send-to-kanban",
        json={"board_slug": "kb-main"},
    )
    assert resp.status_code == 404


def test_send_to_kanban_409_when_not_pending(
    client: TestClient, data_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_improvement_page(data_dir, "Foo", status="not_processed")
    _patch_list_boards(
        monkeypatch, [_kanban.Board(slug="kb-main", name="KB Main", counts={})]
    )
    resp = client.post("/api/pages/Foo/send-to-kanban", json={"board_slug": "kb-main"})
    assert resp.status_code == 409
    assert "pending_for_approve" in resp.json()["detail"]


def test_send_to_kanban_400_when_board_unknown(
    client: TestClient, data_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_improvement_page(data_dir, "Foo")
    _patch_list_boards(
        monkeypatch, [_kanban.Board(slug="kb-main", name="KB Main", counts={})]
    )
    resp = client.post("/api/pages/Foo/send-to-kanban", json={"board_slug": "kb-other"})
    assert resp.status_code == 400


def test_send_to_kanban_503_when_hermes_down(
    client: TestClient, data_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_improvement_page(data_dir, "Foo")

    def boom():
        raise _kanban.HermesUnavailable("daemon down")

    monkeypatch.setattr(_kanban, "list_boards", boom)
    resp = client.post("/api/pages/Foo/send-to-kanban", json={"board_slug": "kb-main"})
    assert resp.status_code == 503


def test_send_to_kanban_rollback_success_returns_500(
    client: TestClient, data_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Frontmatter write fails, archive succeeds → 500 with detail-only body."""
    _write_improvement_page(data_dir, "Foo")
    _patch_list_boards(
        monkeypatch, [_kanban.Board(slug="kb-main", name="KB Main", counts={})]
    )
    monkeypatch.setattr(
        _kanban,
        "create_card",
        lambda **kwargs: _kanban.Card(task_id="t_orphan", board=kwargs["board_slug"]),
    )

    def fail_append(page_path, dispatch_entry):
        raise OSError("disk full")

    archived: list[str] = []

    def ok_archive(task_id):
        archived.append(task_id)

    monkeypatch.setattr(_kanban, "append_dispatch", fail_append)
    monkeypatch.setattr(_kanban, "archive_card", ok_archive)

    resp = client.post("/api/pages/Foo/send-to-kanban", json={"board_slug": "kb-main"})
    assert resp.status_code == 500
    assert archived == ["t_orphan"]
    body = resp.json()
    assert body["detail"] == "frontmatter write failed, kanban card rolled back"
    assert "orphan_task_id" not in body


def test_send_to_kanban_rollback_failure_includes_orphan_task_id(
    client: TestClient, data_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Both frontmatter write and archive fail → 500 with orphan_task_id."""
    _write_improvement_page(data_dir, "Foo")
    _patch_list_boards(
        monkeypatch, [_kanban.Board(slug="kb-main", name="KB Main", counts={})]
    )
    monkeypatch.setattr(
        _kanban,
        "create_card",
        lambda **kwargs: _kanban.Card(task_id="t_orphan", board=kwargs["board_slug"]),
    )

    def fail_append(page_path, dispatch_entry):
        raise OSError("disk full")

    def fail_archive(task_id):
        raise _kanban.HermesRejected("archive refused")

    monkeypatch.setattr(_kanban, "append_dispatch", fail_append)
    monkeypatch.setattr(_kanban, "archive_card", fail_archive)

    resp = client.post("/api/pages/Foo/send-to-kanban", json={"board_slug": "kb-main"})
    assert resp.status_code == 500
    body = resp.json()
    assert body["orphan_task_id"] == "t_orphan"
    assert "t_orphan" in body["detail"]
    assert "hermes kanban archive" in body["detail"]


def test_send_to_kanban_invalidates_cache_on_success(
    client: TestClient, data_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_improvement_page(data_dir, "Foo")
    state = _patch_list_boards(
        monkeypatch, [_kanban.Board(slug="kb-main", name="KB Main", counts={})]
    )
    monkeypatch.setattr(
        _kanban,
        "create_card",
        lambda **kwargs: _kanban.Card(task_id="t_abc", board=kwargs["board_slug"]),
    )

    # Prime the cache.
    client.get("/api/kanban/boards")
    assert state["calls"] == 1

    # Successful POST should invalidate.
    resp = client.post("/api/pages/Foo/send-to-kanban", json={"board_slug": "kb-main"})
    assert resp.status_code == 200

    # Next GET re-fetches.
    client.get("/api/kanban/boards")
    # Two real fetches total: one for the POST (it also consults the
    # cache), and one after invalidation. We assert strict-monotonic
    # growth rather than an exact count to avoid coupling to the
    # internal call sites.
    assert state["calls"] >= 2


# ---------------------------------------------------------------------------
# Lint integration: kanban_dispatches on a page does not break lint.
# ---------------------------------------------------------------------------


def test_lint_accepts_kanban_dispatches_field(tmp_path: Path) -> None:
    """Lint has no allowed-key allowlist, so the field passes through."""
    from kb_mcp.cli.lint_wiki import LintResult, lint

    wiki = tmp_path / "wiki"
    page = wiki / "improvements" / "2026-05" / "Foo.md"
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text(
        "---\n"
        "type: improvement\n"
        "review_status: pending_for_approve\n"
        "kind: improvement\n"
        'observed_at: "2026-05-26"\n'
        "domain: dx\n"
        "severity: low\n"
        "issue_status: open\n"
        "related: []\n"
        'created: "2026-05-19"\n'
        'updated: "2026-05-19"\n'
        "sources: []\n"
        "tags: []\n"
        "kanban_dispatches:\n"
        '  - task_id: "t_abc"\n'
        '    board: "kb-main"\n'
        '    dispatched_at: "2026-05-26T10:23:00+09:00"\n'
        "    direction: null\n"
        "---\n"
        "\n# Foo\n\n"
        "Body paragraph long enough to clear the stub threshold. " * 5
    )
    result = LintResult()
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    lint(result, wiki_dir=wiki, raw_dir=raw_dir)
    # No errors specifically about kanban_dispatches; lint may flag
    # other unrelated things like orphan/INDEX which we ignore.
    bad = [e for e in result.errors if "kanban_dispatches" in e]
    assert bad == [], f"unexpected errors mentioning kanban_dispatches: {bad}"
