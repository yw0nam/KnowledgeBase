"""CRUD for ``pages`` + its join tables. Function-style, like the other repos.

``upsert_page`` is keyed on ``stem`` (the natural identity for import
re-runs). Join rows are REPLACED wholesale on each upsert, not merged —
the caller passes the full desired set. Cascade on the FK clears join
rows when a page is deleted.
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session

from kb.db.models import Page, PageAlias, PageSource, PageTag

_JOIN = {"tags": PageTag, "sources": PageSource, "aliases": PageAlias}
_JOIN_COL = {"tags": PageTag.tag, "sources": PageSource.source, "aliases": PageAlias.alias}


def get_by_stem(session: Session, stem: str) -> Page | None:
    return session.execute(
        select(Page).where(Page.stem == stem)
    ).scalar_one_or_none()


def _replace_join(session: Session, page_id: int, kind: str, values: Sequence[str]) -> None:
    model = _JOIN[kind]
    session.execute(delete(model).where(model.page_id == page_id))
    seen: set[str] = set()
    for v in values:
        if v in seen:
            continue
        seen.add(v)
        session.add(model(page_id=page_id, **{_field(kind): v}))


def _field(kind: str) -> str:
    return {"tags": "tag", "sources": "source", "aliases": "alias"}[kind]


def _get_join(session: Session, page_id: int, kind: str) -> list[str]:
    col = _JOIN_COL[kind]
    model = _JOIN[kind]
    rows = session.execute(
        select(col).where(model.page_id == page_id).order_by(col)
    ).scalars().all()
    return list(rows)


def get_tags(session: Session, page_id: int) -> list[str]:
    return _get_join(session, page_id, "tags")


def get_sources(session: Session, page_id: int) -> list[str]:
    return _get_join(session, page_id, "sources")


def get_aliases(session: Session, page_id: int) -> list[str]:
    return _get_join(session, page_id, "aliases")


def upsert_page(
    session: Session,
    *,
    stem: str,
    rel_path: str,
    typed: dict,
    tags: Sequence[str],
    sources: Sequence[str],
    aliases: Sequence[str],
    extra: dict,
) -> Page:
    """Insert or update the page row keyed on ``stem``; replace join rows."""
    row = get_by_stem(session, stem)
    if row is None:
        row = Page(stem=stem, rel_path=rel_path)
        session.add(row)
    row.rel_path = rel_path
    for col in ("type", "subtype", "category", "review_status",
                "period_start", "period_end", "created", "updated"):
        setattr(row, col, typed.get(col))
    row.extra = extra or None
    session.flush()  # assigns row.id for the join writes
    _replace_join(session, row.id, "tags", tags)
    _replace_join(session, row.id, "sources", sources)
    _replace_join(session, row.id, "aliases", aliases)
    session.commit()
    session.refresh(row)
    return row


def delete_by_stem(session: Session, stem: str) -> None:
    """Delete the page; FK cascade clears join rows."""
    row = get_by_stem(session, stem)
    if row is None:
        return
    # Ensure cascade fires (PRAGMA foreign_keys is ON per kb.db engine).
    session.execute(text("PRAGMA foreign_keys = ON"))
    session.delete(row)
    session.commit()
