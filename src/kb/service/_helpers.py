"""Shared page/revision/export helpers for the service layer.

Extracted verbatim from ``kb.web.routes.db_canonical``, with HTTP specifics
removed.  HTTP callers (the route module) keep their own copies until the
teardown task removes them.
"""

from __future__ import annotations

__all__ = [
    "commit_and_export",
    "_first_heading",
    "_page_payload",
    "_append_revision",
    "_sync_page_frontmatter",
    "_diff_page_fields",
    "_refresh_page_sources",
    "_next_revision_number",
]

from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from kb.db.models import Page, PageRevision, PageSource, RawSource
from kb.service._time import now_iso_kst
from kb.service.errors import ServiceError
from kb.service.export import export_all, record_export_failure


def _first_heading(body: str, fallback: str) -> str:
    for line in body.splitlines():
        if line.startswith("# "):
            return line[2:].strip() or fallback
    return fallback


def _page_payload(row: Page) -> dict:
    return {
        "id": row.id,
        "slug": row.slug,
        "title": row.title,
        "type": row.type,
        "category": row.category,
        "review_status": row.review_status,
        "origin": row.origin,
        "frontmatter": row.frontmatter,
        "body": row.body_md,
        "export_path": row.export_path,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def commit_and_export(session: Session, data_dir: Path, response: dict) -> dict:
    """Commit the write, export Markdown, and annotate the response.

    Generalizes the route's ``_commit_export_or_500``: on export failure,
    records it and raises ``ServiceError("export_failed", ...)`` instead of
    ``HTTPException(500)``.
    """
    session.commit()
    try:
        written = export_all(session, data_dir)
    except Exception as exc:  # noqa: BLE001
        record_export_failure(session, str(exc))
        response["export"] = {"status": "failed", "db_written": True, "error": str(exc)}
        raise ServiceError("export_failed", response)
    response["export"] = {"status": "success", "written": written}
    return response


def _next_revision_number(session: Session, page_id: int) -> int:
    current = session.execute(
        select(func.max(PageRevision.revision_number)).where(
            PageRevision.page_id == page_id
        )
    ).scalar_one()
    return 1 if current is None else int(current) + 1


def _append_revision(
    session: Session,
    page: Page,
    *,
    change_kind: str,
    changed_fields: dict | None,
    source: str,
    note: str | None = None,
) -> None:
    session.add(
        PageRevision(
            page_id=page.id,
            revision_number=_next_revision_number(session, page.id),
            change_kind=change_kind,
            body_md=page.body_md,
            frontmatter=page.frontmatter,
            changed_fields=changed_fields,
            created_at=now_iso_kst(),
            source=source,
            note=note,
        )
    )


def _sync_page_frontmatter(page: Page, fields: dict) -> None:
    fm = dict(page.frontmatter)
    for key, value in fields.items():
        if value is None:
            fm.pop(key, None)
        else:
            fm[key] = value
    page.frontmatter = fm


def _diff_page_fields(page: Page, new: dict) -> dict:
    """Return ``{field: {old, new}}`` for page columns whose value changes."""
    changed: dict[str, dict] = {}
    for field, value in new.items():
        old = getattr(page, field)
        if old != value:
            changed[field] = {"old": old, "new": value}
    return changed


def _refresh_page_sources(session: Session, page: Page) -> None:
    session.query(PageSource).filter(PageSource.page_id == page.id).delete()
    seen: set[str] = set()
    for source in page.frontmatter.get("sources") or []:
        citation = str(source)
        if citation in seen:
            continue
        seen.add(citation)
        raw = session.execute(
            select(RawSource).where(RawSource.source_key == citation)
        ).scalar_one_or_none()
        session.add(
            PageSource(
                page_id=page.id,
                raw_source_id=raw.id if raw is not None else None,
                citation_path=citation,
                created_at=now_iso_kst(),
            )
        )
