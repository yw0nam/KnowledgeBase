"""Unit tests for ``kb.cli.wiki_review._kanban``.

Covers:
- ``list_boards``: subprocess JSON parsing.
- ``create_card``: success, non-zero exit, timeout, ``id``→``task_id``
  normalisation, sparse ``counts``.
- ``archive_card``: passthrough.
- ``append_dispatch``: creates list when absent, appends when present,
  preserves body verbatim and other frontmatter keys.

Subprocess is mocked via ``monkeypatch`` on ``subprocess.run`` inside
the ``_kanban`` module — the patch must shadow the bound reference, not
the global, since the helper imports ``subprocess`` at module top.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
import yaml

from kb.cli.wiki_review import _kanban


class _FakeCompleted:
    def __init__(self, returncode: int = 0, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _patch_run(monkeypatch: pytest.MonkeyPatch, fake) -> list[list[str]]:
    """Install ``fake`` as ``subprocess.run`` in ``_kanban`` and capture calls."""
    calls: list[list[str]] = []

    def runner(args, **kwargs):
        calls.append(list(args))
        if callable(fake):
            return fake(args, **kwargs)
        return fake

    monkeypatch.setattr(_kanban.subprocess, "run", runner)
    return calls


# ---------------------------------------------------------------------------
# list_boards
# ---------------------------------------------------------------------------


def test_list_boards_parses_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = [
        {
            "slug": "kb-main",
            "name": "KB Main",
            "counts": {"ready": 3, "in_progress": 1},
        },
        {"slug": "kb-spike", "name": "KB Spike", "counts": {}},
    ]
    _patch_run(monkeypatch, _FakeCompleted(stdout=json.dumps(payload)))

    boards = _kanban.list_boards()

    assert len(boards) == 2
    assert boards[0] == _kanban.Board(
        slug="kb-main", name="KB Main", counts={"ready": 3, "in_progress": 1}
    )
    assert boards[1].counts == {}


def test_list_boards_unavailable_when_binary_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raises(args, **kwargs):
        raise FileNotFoundError("hermes")

    monkeypatch.setattr(_kanban.subprocess, "run", raises)
    with pytest.raises(_kanban.HermesUnavailable):
        _kanban.list_boards()


def test_list_boards_unavailable_on_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    def raises(args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=args, timeout=10)

    monkeypatch.setattr(_kanban.subprocess, "run", raises)
    with pytest.raises(_kanban.HermesUnavailable):
        _kanban.list_boards()


def test_list_boards_rejected_on_nonzero_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_run(
        monkeypatch,
        _FakeCompleted(returncode=1, stderr="daemon offline"),
    )
    with pytest.raises(_kanban.HermesRejected, match="daemon offline"):
        _kanban.list_boards()


def test_list_boards_rejected_on_non_json(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_run(monkeypatch, _FakeCompleted(stdout="not-json"))
    with pytest.raises(_kanban.HermesRejected, match="non-JSON"):
        _kanban.list_boards()


# ---------------------------------------------------------------------------
# create_card
# ---------------------------------------------------------------------------


def test_create_card_normalises_id_to_task_id(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {"id": "t_abc123", "board": "kb-main", "title": "x"}
    calls = _patch_run(monkeypatch, _FakeCompleted(stdout=json.dumps(payload)))

    card = _kanban.create_card("kb-main", "Title", "Body")
    assert card == _kanban.Card(task_id="t_abc123", board="kb-main")

    # The CLI invocation has no --metadata flag — verify that.
    cmd = calls[0]
    assert "hermes" in cmd[0]
    assert "--metadata" not in cmd
    assert "--json" in cmd
    assert "--board" in cmd
    assert "kb-main" in cmd
    # `--board` must come BEFORE `create` (it's a flag on the
    # `kanban` parent subcommand, not on `create`). Otherwise
    # hermes errors with "unrecognized arguments: --board ...".
    kanban_idx = cmd.index("kanban")
    board_idx = cmd.index("--board")
    create_idx = cmd.index("create")
    assert kanban_idx < board_idx < create_idx


def test_create_card_rejected_on_nonzero_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_run(
        monkeypatch,
        _FakeCompleted(returncode=2, stderr="board kb-bad not found"),
    )
    with pytest.raises(_kanban.HermesRejected, match="board kb-bad not found"):
        _kanban.create_card("kb-bad", "T", "B")


def test_create_card_unavailable_on_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    def raises(args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=args, timeout=10)

    monkeypatch.setattr(_kanban.subprocess, "run", raises)
    with pytest.raises(_kanban.HermesUnavailable):
        _kanban.create_card("kb-main", "T", "B")


def test_create_card_rejected_when_id_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_run(monkeypatch, _FakeCompleted(stdout=json.dumps({"board": "kb-main"})))
    with pytest.raises(_kanban.HermesRejected, match="missing `id`"):
        _kanban.create_card("kb-main", "T", "B")


# ---------------------------------------------------------------------------
# archive_card
# ---------------------------------------------------------------------------


def test_archive_card_passes_id(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _patch_run(monkeypatch, _FakeCompleted(stdout="Archived t_abc"))
    _kanban.archive_card("t_abc")
    assert calls[0] == ["hermes", "kanban", "archive", "t_abc"]


def test_archive_card_propagates_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_run(monkeypatch, _FakeCompleted(returncode=1, stderr="no such task"))
    with pytest.raises(_kanban.HermesRejected, match="no such task"):
        _kanban.archive_card("t_bad")


# ---------------------------------------------------------------------------
# append_dispatch
# ---------------------------------------------------------------------------


def _write_page(path: Path, fm: dict, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fm_block = yaml.safe_dump(fm, sort_keys=False)
    path.write_text(f"---\n{fm_block}---\n{body}")


def test_append_dispatch_creates_list_when_absent(tmp_path: Path) -> None:
    page = tmp_path / "Foo.md"
    _write_page(
        page,
        {
            "type": "improvement",
            "review_status": "pending_for_approve",
            "tags": ["x"],
        },
        "\n# Foo\n\nBody.\n",
    )
    entry = {
        "task_id": "t_1",
        "board": "kb-main",
        "dispatched_at": "2026-05-26T10:23:00+09:00",
        "direction": None,
    }
    _kanban.append_dispatch(page, entry)

    fm = yaml.safe_load(page.read_text().split("---")[1])
    assert fm["kanban_dispatches"] == [entry]
    # Untouched keys remain.
    assert fm["type"] == "improvement"
    assert fm["review_status"] == "pending_for_approve"
    assert fm["tags"] == ["x"]
    # Body preserved.
    assert "# Foo" in page.read_text()
    assert "Body." in page.read_text()


def test_append_dispatch_appends_when_present(tmp_path: Path) -> None:
    page = tmp_path / "Foo.md"
    existing = {
        "task_id": "t_old",
        "board": "kb-main",
        "dispatched_at": "2026-05-20T10:00:00+09:00",
        "direction": "first pass",
    }
    _write_page(
        page,
        {
            "type": "improvement",
            "review_status": "pending_for_approve",
            "kanban_dispatches": [existing],
        },
        "\n# Foo\n",
    )
    new = {
        "task_id": "t_new",
        "board": "kb-main",
        "dispatched_at": "2026-05-26T10:23:00+09:00",
        "direction": None,
    }
    _kanban.append_dispatch(page, new)

    fm = yaml.safe_load(page.read_text().split("---")[1])
    assert fm["kanban_dispatches"] == [existing, new]


def test_append_dispatch_atomic_write_no_leftover_tmp(tmp_path: Path) -> None:
    page = tmp_path / "Foo.md"
    _write_page(
        page,
        {"type": "improvement", "review_status": "pending_for_approve"},
        "\n# Foo\n",
    )
    _kanban.append_dispatch(
        page,
        {
            "task_id": "t_x",
            "board": "kb-main",
            "dispatched_at": "2026-05-26T10:23:00+09:00",
            "direction": None,
        },
    )
    # No stale tempfile siblings.
    leftovers = [
        p for p in tmp_path.iterdir() if p.name.startswith(".Foo.md.") and p.is_file()
    ]
    assert leftovers == []


def test_append_dispatch_errors_on_missing_frontmatter(tmp_path: Path) -> None:
    page = tmp_path / "Foo.md"
    page.write_text("no frontmatter here\n")
    with pytest.raises(ValueError):
        _kanban.append_dispatch(
            page,
            {
                "task_id": "t_x",
                "board": "kb-main",
                "dispatched_at": "2026-05-26T10:23:00+09:00",
                "direction": None,
            },
        )
