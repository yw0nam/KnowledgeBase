"""Contract test for ``GET /api/dashboard``.

Locks the *shape* of the dashboard response so future refactors can't
silently rename a top-level key or drop a list-element field. The
frontend dashboard (Phase D-1/D-2) reads this endpoint directly and has
no schema enforcement on the wire — this test is that schema.

Strategy
--------
Build a hermetic ``data/`` tree under ``tmp_path`` and point the web app
at it via the ``KB_DATA_DIR`` environment variable (the supported hook
in ``kb_mcp.web.config.load``). ``create_app()`` is then called fresh
so config is re-read; ``TestClient`` exercises the real route against
the real aggregator. Asserts are on SHAPE not VALUES — counts, rates
and dates can drift without breaking the contract.
"""

from __future__ import annotations

import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

KST = ZoneInfo("Asia/Seoul")


# ---------------------------------------------------------------------------
# Fixture corpus builders
# ---------------------------------------------------------------------------


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def _build_corpus(data_dir: Path) -> None:
    """Populate a minimal hermetic ``data/`` tree.

    Timestamps are anchored to "now in KST" so the fixture stays in the
    8-week window regardless of when the test runs. The not_processed
    page is created 5 days ago so its auto-reject ETA is ~2 days out
    (inside the 72-hour EXPIRING_WINDOW_HOURS).
    """
    now = datetime.datetime.now(KST)
    today = now.date()
    five_days_ago = today - datetime.timedelta(days=5)
    two_days_ago = now - datetime.timedelta(days=2)

    # Approved entity inside the window.
    _write(
        data_dir / "wiki" / "entities" / "Subj" / "2026-05" / "test_entity.md",
        (
            "---\n"
            "type: entity\n"
            "review_status: approved\n"
            f'created: "{five_days_ago.isoformat()}"\n'
            f'updated: "{today.isoformat()}"\n'
            f'approved_at: "{two_days_ago.isoformat(timespec="seconds")}"\n'
            "sources:\n"
            "  - raw/manual/test.md\n"
            "aliases: []\n"
            "tags: []\n"
            "---\n"
            "\n# Test Entity\n\nBody paragraph.\n"
        ),
    )

    # not_processed concept inside the 72h auto-reject window.
    _write(
        data_dir / "wiki" / "concepts" / "test_concept.md",
        (
            "---\n"
            "type: concept\n"
            "review_status: not_processed\n"
            f'created: "{five_days_ago.isoformat()}"\n'
            f'updated: "{five_days_ago.isoformat()}"\n'
            "sources:\n"
            "  - raw/conversations/test.md\n"
            "tags: []\n"
            "---\n"
            "\n# Test Concept\n\nBody paragraph.\n"
        ),
    )

    # User-rejected concept inside the window, with a User Feedback section.
    _write(
        data_dir / "rejected" / "concepts" / "test_rejected.md",
        (
            "---\n"
            "type: concept\n"
            "review_status: rejected\n"
            f'created: "{five_days_ago.isoformat()}"\n'
            f'updated: "{today.isoformat()}"\n'
            f'rejected_at: "{two_days_ago.isoformat(timespec="seconds")}"\n'
            "rejected_by: user\n"
            "sources:\n"
            "  - raw/conversations/y.md\n"
            "tags: []\n"
            "---\n"
            "\n# Test Rejected\n\nBody.\n"
            "\n## User Feedback\n"
            f"\n{today.isoformat()}-Rejected: insufficient sources.\n"
        ),
    )

    # log.md with a recent heading so is_stale is well-defined.
    _write(
        data_dir / "log.md",
        f"# KnowledgeBase Operation Log\n\n## {today.isoformat()}\n\n- seeded fixture.\n",
    )


# ---------------------------------------------------------------------------
# Client fixture
# ---------------------------------------------------------------------------


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    data_dir = tmp_path / "data"
    _build_corpus(data_dir)
    monkeypatch.setenv("KB_DATA_DIR", str(data_dir))
    # Import + create_app inside the fixture so config.load() picks up
    # the patched env var. Module-level ``app = create_app()`` in
    # ``kb_mcp.web.app`` is bypassed by calling create_app() again.
    from kb_mcp.web.app import create_app

    return TestClient(create_app())


# ---------------------------------------------------------------------------
# Contract assertions
# ---------------------------------------------------------------------------


def _assert_keys(d: dict, expected: set[str], label: str) -> None:
    missing = expected - set(d)
    assert not missing, f"{label}: missing keys {sorted(missing)} (got {sorted(d)})"


def test_dashboard_top_level_contract(client: TestClient) -> None:
    """Every documented top-level key is present and well-typed."""
    resp = client.get("/api/dashboard?window=8")
    assert resp.status_code == 200, resp.text
    payload = resp.json()

    _assert_keys(
        payload,
        {
            "window",
            "meta",
            "activity",
            "rejection_by_type",
            "rejection_by_source_kind",
            "rejection_by_type_and_source",
            "auto_reject_soon",
            "recent_rejections",
        },
        "top-level",
    )
    assert isinstance(payload["activity"], list)
    assert isinstance(payload["rejection_by_type"], list)
    assert isinstance(payload["rejection_by_source_kind"], list)
    assert isinstance(payload["rejection_by_type_and_source"], dict)
    assert isinstance(payload["auto_reject_soon"], list)
    assert isinstance(payload["recent_rejections"], list)


def test_dashboard_window_and_meta_sub_shape(client: TestClient) -> None:
    payload = client.get("/api/dashboard?window=8").json()

    window = payload["window"]
    _assert_keys(window, {"weeks", "from", "to"}, "window")
    assert window["weeks"] == 8
    assert isinstance(window["from"], str)
    assert isinstance(window["to"], str)

    meta = payload["meta"]
    _assert_keys(
        meta, {"data_dir", "auto_reject_ttl_days", "log_last_entry", "is_stale"}, "meta"
    )
    assert isinstance(meta["data_dir"], str)
    assert isinstance(meta["auto_reject_ttl_days"], int)
    assert meta["log_last_entry"] is None or isinstance(meta["log_last_entry"], str)
    assert isinstance(meta["is_stale"], bool)


def test_dashboard_activity_row_shape(client: TestClient) -> None:
    """activity is one row per ISO week — N weeks → N or N+1 rows."""
    payload = client.get("/api/dashboard?window=8").json()
    activity = payload["activity"]
    assert activity, "fixture should produce a non-empty activity series"
    for row in activity:
        _assert_keys(
            row,
            {"week_start", "approved", "rejected_user", "rejected_auto_ttl"},
            "activity row",
        )
        assert isinstance(row["week_start"], str)
        for counter in ("approved", "rejected_user", "rejected_auto_ttl"):
            assert isinstance(row[counter], int)
            assert row[counter] >= 0


def test_dashboard_rejection_by_type_row_shape(client: TestClient) -> None:
    payload = client.get("/api/dashboard?window=8").json()
    rows = payload["rejection_by_type"]
    assert rows, "canonical-type rows are always emitted, even if all zero"
    for row in rows:
        _assert_keys(
            row, {"type", "rejected", "total", "rate"}, "rejection_by_type row"
        )
        assert isinstance(row["type"], str)
        assert isinstance(row["rejected"], int) and row["rejected"] >= 0
        assert isinstance(row["total"], int) and row["total"] >= 0
        assert isinstance(row["rate"], float)
        assert 0.0 <= row["rate"] <= 1.0


def test_dashboard_rejection_by_source_kind_row_shape(client: TestClient) -> None:
    payload = client.get("/api/dashboard?window=8").json()
    rows = payload["rejection_by_source_kind"]
    assert rows
    for row in rows:
        _assert_keys(
            row, {"kind", "rejected", "total", "rate"}, "rejection_by_source_kind row"
        )
        assert isinstance(row["kind"], str)
        assert isinstance(row["rejected"], int) and row["rejected"] >= 0
        assert isinstance(row["total"], int) and row["total"] >= 0
        assert isinstance(row["rate"], float)
        assert 0.0 <= row["rate"] <= 1.0


def test_dashboard_type_and_source_matrix_shape(client: TestClient) -> None:
    payload = client.get("/api/dashboard?window=8").json()
    matrix = payload["rejection_by_type_and_source"]
    _assert_keys(matrix, {"types", "source_kinds", "cells"}, "type×source matrix")
    assert isinstance(matrix["types"], list) and all(
        isinstance(t, str) for t in matrix["types"]
    )
    assert isinstance(matrix["source_kinds"], list) and all(
        isinstance(k, str) for k in matrix["source_kinds"]
    )
    assert isinstance(matrix["cells"], list)
    # The fixture has events for at least one (type, source_kind) pair,
    # so cells should be non-empty — exercises cell shape.
    assert matrix["cells"], "fixture should produce at least one matrix cell"
    for cell in matrix["cells"]:
        _assert_keys(
            cell,
            {"type", "source_kind", "approved", "rejected", "total", "rate"},
            "matrix cell",
        )
        assert isinstance(cell["type"], str)
        assert isinstance(cell["source_kind"], str)
        assert isinstance(cell["approved"], int) and cell["approved"] >= 0
        assert isinstance(cell["rejected"], int) and cell["rejected"] >= 0
        assert isinstance(cell["total"], int) and cell["total"] >= 0
        assert isinstance(cell["rate"], float)
        assert 0.0 <= cell["rate"] <= 1.0


def test_dashboard_auto_reject_soon_row_shape(client: TestClient) -> None:
    payload = client.get("/api/dashboard?window=8").json()
    rows = payload["auto_reject_soon"]
    assert rows, "fixture concept page is within the 72h auto-reject window"
    for row in rows:
        _assert_keys(
            row,
            {
                "stem",
                "rel_path",
                "type",
                "title",
                "created_at",
                "auto_reject_at",
                "hours_remaining",
            },
            "auto_reject_soon row",
        )
        assert isinstance(row["stem"], str)
        assert isinstance(row["rel_path"], str)
        assert row["rel_path"].startswith("wiki/")
        assert isinstance(row["type"], str)
        assert isinstance(row["title"], str)
        assert isinstance(row["created_at"], str)
        assert isinstance(row["auto_reject_at"], str)
        assert isinstance(row["hours_remaining"], int)
        assert 0 < row["hours_remaining"] <= 72


def test_dashboard_recent_rejections_row_shape(client: TestClient) -> None:
    payload = client.get("/api/dashboard?window=8").json()
    rows = payload["recent_rejections"]
    assert rows, "fixture rejected/ page should appear in recent_rejections"
    for row in rows:
        _assert_keys(
            row,
            {
                "stem",
                "title",
                "type",
                "source_kinds",
                "rejected_at",
                "rejected_by",
                "feedback_excerpt",
            },
            "recent_rejections row",
        )
        assert isinstance(row["stem"], str)
        assert isinstance(row["title"], str)
        assert isinstance(row["type"], str)
        assert isinstance(row["source_kinds"], list)
        assert all(isinstance(k, str) for k in row["source_kinds"])
        assert isinstance(row["rejected_at"], str)
        assert row["rejected_by"] in ("user", "auto_ttl", "")
        assert isinstance(row["feedback_excerpt"], str)


@pytest.mark.parametrize("bad_window", [999, 3, 0, -1, 100])
def test_dashboard_rejects_unknown_window(client: TestClient, bad_window: int) -> None:
    """ALLOWED_WINDOWS = {4, 8, 12, 24}; everything else is 4xx (422)."""
    resp = client.get(f"/api/dashboard?window={bad_window}")
    assert 400 <= resp.status_code < 500
    assert resp.status_code == 422
