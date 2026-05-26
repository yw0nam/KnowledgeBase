"""CRUD helpers for the append-only ``wiki_edits`` audit table.

Function-style — the route layer composes these directly. The schema
ships with ``trg_wiki_edits_no_update`` / ``trg_wiki_edits_no_delete``
triggers, so any UPDATE/DELETE attempt raises ``IntegrityError`` at the
DB layer; no application-side enforcement is needed.
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from kb.db.models import WikiEdit


def insert_edits(
    session: Session,
    *,
    page_stem: str,
    changes: Sequence[tuple[str, object, object]],
    edited_at: str,
    source: str = "console",
) -> list[WikiEdit]:
    """Insert one row per ``(field, old_value, new_value)`` change.

    All rows commit in a single transaction. The caller's session is
    left rolled back on any failure — routes that wrote the markdown
    file before calling this must surface the gap to the operator
    rather than retrying silently (spec §6.4 recovery contract).
    """
    rows = [
        WikiEdit(
            page_stem=page_stem,
            field=field,
            old_value=old_value,
            new_value=new_value,
            edited_at=edited_at,
            source=source,
        )
        for field, old_value, new_value in changes
    ]
    session.add_all(rows)
    session.commit()
    for r in rows:
        session.refresh(r)
    return rows


def list_edits(
    session: Session,
    *,
    page_stem: str,
    since: str | None = None,
    limit: int | None = None,
) -> tuple[list[WikiEdit], int]:
    """Descending list of edits for ``page_stem`` with a ``since`` cutoff.

    ``since`` is treated as a strict-less-than cursor on ``edited_at``
    so a client paging through history can pass the last ``edited_at``
    it saw to fetch the next page without overlap.

    Total count is the unfiltered count for ``page_stem`` so the UI
    can render "showing N of M" without a second round-trip.
    """
    capped = 50 if limit is None else max(1, min(int(limit), 200))

    total = int(
        session.execute(
            select(func.count(WikiEdit.id)).where(WikiEdit.page_stem == page_stem)
        ).scalar_one()
    )

    q = select(WikiEdit).where(WikiEdit.page_stem == page_stem)
    if since is not None:
        q = q.where(WikiEdit.edited_at < since)
    q = q.order_by(WikiEdit.edited_at.desc(), WikiEdit.id.desc()).limit(capped)
    rows = list(session.execute(q).scalars().all())
    return rows, total
