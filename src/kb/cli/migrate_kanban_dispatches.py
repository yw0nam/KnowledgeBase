"""One-shot backfill: ``kanban_dispatches`` frontmatter → ``dispatches`` table.

Per spec §8: for every wiki page that still has a
``kanban_dispatches`` list, insert one ``dispatches`` row per entry
and remove the frontmatter key. Idempotent — re-runs are no-ops
because the UNIQUE constraint blocks duplicates and the key removal
makes a second sweep find nothing.

Operator-invoked, not automatic. Documented in CHANGELOG.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import yaml
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from kb import REPO_ROOT
from kb.cli.wiki_review._store import _split_frontmatter
from kb.db import make_engine, make_session_factory
from kb.db.repos import dispatch_repo


def _data_dir() -> Path:
    return Path(os.environ.get("KB_DATA_DIR", REPO_ROOT / "data")).resolve()


def _rewrite_frontmatter(page: Path, fm: dict, body: str) -> None:
    """Re-serialise frontmatter and atomically replace the page."""
    fm_block = yaml.safe_dump(
        fm, sort_keys=False, allow_unicode=True, default_flow_style=False
    )
    new_text = f"---\n{fm_block}---{body}"

    fd, tmp_path = tempfile.mkstemp(
        prefix=f".{page.name}.", suffix=".tmp", dir=str(page.parent)
    )
    try:
        with os.fdopen(fd, "w") as fh:
            fh.write(new_text)
        os.replace(tmp_path, page)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _backfill_page(session: Session, page: Path, data_dir: Path) -> tuple[int, int]:
    """Return ``(inserted, skipped)`` for this page."""
    text = page.read_text()
    parts = _split_frontmatter(text)
    if parts is None:
        return 0, 0
    fm_block, body = parts
    try:
        fm = yaml.safe_load(fm_block) or {}
    except yaml.YAMLError:
        return 0, 0
    if not isinstance(fm, dict):
        return 0, 0

    entries = fm.get("kanban_dispatches")
    if not isinstance(entries, list) or not entries:
        return 0, 0

    try:
        rel_path = page.relative_to(data_dir)
    except ValueError:
        rel_path = page

    inserted = 0
    skipped = 0
    for entry in entries:
        if not isinstance(entry, dict):
            skipped += 1
            continue
        task_id = entry.get("task_id")
        board = entry.get("board")
        dispatched_at = entry.get("dispatched_at")
        if not (
            isinstance(task_id, str)
            and isinstance(board, str)
            and isinstance(dispatched_at, str)
        ):
            skipped += 1
            continue
        direction = entry.get("direction")
        if direction is not None and not isinstance(direction, str):
            direction = None
        try:
            dispatch_repo.create_dispatch(
                session,
                page_stem=page.stem,
                page_path_at_dispatch=str(rel_path),
                external_board_id=board,
                external_task_id=task_id,
                direction=direction,
                idempotency_key=None,
                created_at=dispatched_at,
                dispatched_at=dispatched_at,
            )
            inserted += 1
        except IntegrityError:
            session.rollback()
            skipped += 1

    # Strip the key whether we inserted, skipped, or both.
    del fm["kanban_dispatches"]
    _rewrite_frontmatter(page, fm, body)
    return inserted, skipped


def main() -> int:
    data_dir = _data_dir()
    wiki_dir = data_dir / "wiki"
    if not wiki_dir.exists():
        print(f"No wiki directory at {wiki_dir}; nothing to do.")
        return 0

    engine = make_engine(data_dir)
    factory = make_session_factory(engine)
    session = factory()
    total_inserted = 0
    total_skipped = 0
    try:
        for page in sorted(wiki_dir.rglob("*.md")):
            if page.name in {"_index.md", "INDEX.md"}:
                continue
            inserted, skipped = _backfill_page(session, page, data_dir)
            if inserted or skipped:
                print(
                    f"Processed {page.stem}: inserted {inserted}, " f"skipped {skipped}"
                )
                total_inserted += inserted
                total_skipped += skipped
    finally:
        session.close()
        engine.dispose()

    print(f"Total: inserted {total_inserted}, skipped {total_skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
