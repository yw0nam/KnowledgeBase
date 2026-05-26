"""Tests for the Phase 2 `kb-migrate-kanban-dispatches` backfill CLI.

The CLI must be idempotent: running twice produces the same DB state
and leaves no ``kanban_dispatches`` key in any wiki page. The UNIQUE
constraint on ``(external_board_id, external_task_id)`` blocks
duplicate inserts on a second run; the frontmatter key removal makes
subsequent runs no-ops.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from alembic import command
from alembic.config import Config

from kb import REPO_ROOT
from kb.db import make_engine, make_session_factory
from kb.db.models import Dispatch


def _alembic_cfg() -> Config:
    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "alembic"))
    return cfg


def _write_page_with_dispatches(data_dir: Path, stem: str, entries: list[dict]) -> Path:
    page = data_dir / "wiki" / "improvements" / "2026-05" / f"{stem}.md"
    page.parent.mkdir(parents=True, exist_ok=True)
    fm = {
        "type": "improvement",
        "review_status": "pending_for_approve",
        "kind": "improvement",
        "tags": [],
        "kanban_dispatches": entries,
    }
    fm_block = yaml.safe_dump(fm, sort_keys=False)
    page.write_text(f"---\n{fm_block}---\n\n# {stem}\n\nBody.\n")
    return page


def test_backfill_cli_is_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_dir = tmp_path / "data"
    (data_dir / "wiki").mkdir(parents=True)
    monkeypatch.setenv("KB_DATA_DIR", str(data_dir))

    command.upgrade(_alembic_cfg(), "head")

    entries = [
        {
            "task_id": "t_one",
            "board": "kb-main",
            "dispatched_at": "2026-05-26T10:00:00+09:00",
            "direction": "first pass",
        },
        {
            "task_id": "t_two",
            "board": "kb-main",
            "dispatched_at": "2026-05-26T11:00:00+09:00",
            "direction": None,
        },
    ]
    page = _write_page_with_dispatches(data_dir, "Foo", entries)

    from kb.cli.migrate_kanban_dispatches import main

    main()

    engine = make_engine(data_dir)
    factory = make_session_factory(engine)
    sess = factory()
    try:
        rows = sess.query(Dispatch).order_by(Dispatch.id).all()
        assert len(rows) == 2
        assert {r.external_task_id for r in rows} == {"t_one", "t_two"}
    finally:
        sess.close()
        engine.dispose()

    # Frontmatter key was removed.
    fm_after = yaml.safe_load(page.read_text().split("---")[1])
    assert "kanban_dispatches" not in fm_after

    # Re-add the same entries (simulate operator confusion) and run
    # again. The UNIQUE constraint must block dupes; key must get
    # removed again.
    fm_after["kanban_dispatches"] = entries
    fm_block = yaml.safe_dump(fm_after, sort_keys=False)
    body = page.read_text().split("---", 2)[2]
    page.write_text(f"---\n{fm_block}---{body}")

    main()

    engine = make_engine(data_dir)
    factory = make_session_factory(engine)
    sess = factory()
    try:
        rows = sess.query(Dispatch).all()
        assert len(rows) == 2
    finally:
        sess.close()
        engine.dispose()

    fm_final = yaml.safe_load(page.read_text().split("---")[1])
    assert "kanban_dispatches" not in fm_final
