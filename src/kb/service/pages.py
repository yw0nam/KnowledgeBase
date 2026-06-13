"""Service functions for Page operations.

Extracted from ``kb.web.routes.db_canonical`` route handlers with HTTP
specifics removed. HTTP exceptions become ``ServiceError``; ``data_dir``
replaces ``request.app.state.config.data_dir``.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from kb.db.models import Page
from kb.lint.wiki import validate_page_create
from kb.service._helpers import (
    _append_revision,
    _diff_page_fields,
    _first_heading,
    _page_payload,
    _refresh_page_sources,
    _sync_page_frontmatter,
    commit_and_export,
)
from kb.service._time import date_from_iso, now_iso_kst, today_kst
from kb.service.errors import ServiceError


def upsert_page(
    session: Session,
    data_dir: Path,
    *,
    slug: str,
    type: str,
    body_md: str,
    frontmatter: dict,
    title: str | None = None,
    category: str | None = None,
    review_status: str | None = None,
    origin: str = "ingested",
    export_path: str,
    created_at: str | None = None,
    updated_at: str | None = None,
    source: str = "agent",
) -> dict:
    """Insert or update a Page by slug; run lint before writing."""
    now = now_iso_kst()
    review_status = (
        review_status if review_status is not None else frontmatter.get("review_status")
    )
    title = title or frontmatter.get("title") or _first_heading(body_md, slug)
    category = category or frontmatter.get("category")

    lint = validate_page_create(frontmatter, body_md, session, slug=slug)
    if not lint.ok:
        raise ServiceError(
            "lint_failed", {"errors": lint.errors, "warnings": lint.warnings}
        )

    fields = {
        "title": title,
        "type": type,
        "category": category,
        "review_status": review_status,
        "origin": origin,
        "body_md": body_md,
        "frontmatter": frontmatter,
        "export_path": export_path,
    }

    existing = session.execute(
        select(Page).where(Page.slug == slug)
    ).scalar_one_or_none()

    if existing is None:
        page = Page(
            slug=slug,
            created_at=created_at or now,
            updated_at=updated_at or now,
            **fields,
        )
        session.add(page)
        try:
            session.flush()
        except IntegrityError:
            session.rollback()
            raise ServiceError("conflict", "page already exists")
        _refresh_page_sources(session, page)
        _append_revision(
            session, page, change_kind="create", changed_fields=None, source=source
        )
        return commit_and_export(session, data_dir, {"page": _page_payload(page)})

    page = existing
    changed = _diff_page_fields(page, fields)
    for f, v in fields.items():
        setattr(page, f, v)
    page.updated_at = now
    _refresh_page_sources(session, page)
    _append_revision(
        session,
        page,
        change_kind="update",
        changed_fields=changed or None,
        source=source,
    )
    return commit_and_export(session, data_dir, {"page": _page_payload(page)})


def patch_page(
    session: Session,
    data_dir: Path,
    *,
    slug: str,
    title: str | None = None,
    body_md: str | None = None,
    frontmatter: dict | None = None,
    category: str | None = None,
    review_status: str | None = None,
    source: str = "agent",
    note: str | None = None,
) -> dict:
    """Partially update a Page; skip commit if nothing changed."""
    page = session.execute(select(Page).where(Page.slug == slug)).scalar_one_or_none()
    if page is None:
        raise ServiceError("not_found", "page not found")

    # Snapshot pre-patch values once, before any attribute writes, so the
    # revision's changed_fields["*"]["old"] reflect the true DB state (and
    # don't alias the live SQLAlchemy frontmatter dict).
    old_title = page.title
    old_body = page.body_md
    old_frontmatter = dict(page.frontmatter)
    old_category = page.category
    old_review_status = page.review_status

    changed: dict[str, dict] = {}

    if title is not None and title != old_title:
        changed["title"] = {"old": old_title, "new": title}
        page.title = title

    if body_md is not None and body_md != old_body:
        changed["body_md"] = {"old": old_body, "new": body_md}
        page.body_md = body_md

    if frontmatter is not None and frontmatter != old_frontmatter:
        changed["frontmatter"] = {"old": old_frontmatter, "new": frontmatter}
        page.frontmatter = frontmatter
        if "category" in frontmatter:
            page.category = frontmatter.get("category")
        if "review_status" in frontmatter:
            page.review_status = frontmatter.get("review_status")

    if category is not None and category != old_category:
        changed["category"] = {"old": old_category, "new": category}
        page.category = category
        _sync_page_frontmatter(page, {"category": category})

    if review_status is not None and review_status != old_review_status:
        changed["review_status"] = {"old": old_review_status, "new": review_status}
        page.review_status = review_status
        _sync_page_frontmatter(page, {"review_status": review_status})

    if not changed:
        return {"page": _page_payload(page), "export": {"status": "skipped"}}

    lint = validate_page_create(page.frontmatter, page.body_md, session, slug=page.slug)
    if not lint.ok:
        raise ServiceError(
            "lint_failed", {"errors": lint.errors, "warnings": lint.warnings}
        )

    page.updated_at = now_iso_kst()
    _refresh_page_sources(session, page)
    _append_revision(
        session,
        page,
        change_kind="update",
        changed_fields=changed,
        source=source,
        note=note,
    )
    return commit_and_export(session, data_dir, {"page": _page_payload(page)})


def _transition_page(
    session: Session,
    data_dir: Path,
    *,
    slug: str,
    expected: str,
    new_status: str,
    change_kind: str,
    source: str,
    feedback: str = "",
    extra_fm: dict | None = None,
) -> dict:
    """Shared status-transition logic for promote/approve."""
    page = session.execute(select(Page).where(Page.slug == slug)).scalar_one_or_none()
    if page is None:
        raise ServiceError("not_found", "page not found")
    if page.review_status != expected:
        raise ServiceError(
            "conflict", f"expected {expected}, current {page.review_status!r}"
        )

    changed = {"review_status": {"old": page.review_status, "new": new_status}}
    page.review_status = new_status
    fm_fields = {"review_status": new_status}
    if extra_fm:
        fm_fields.update(extra_fm)
    _sync_page_frontmatter(page, fm_fields)
    page.updated_at = now_iso_kst()
    _append_revision(
        session,
        page,
        change_kind=change_kind,
        changed_fields=changed,
        source=source,
        note=feedback or None,
    )
    return commit_and_export(session, data_dir, {"page": _page_payload(page)})


def promote_page(
    session: Session,
    data_dir: Path,
    *,
    slug: str,
    feedback: str = "",
    source: str = "console",
) -> dict:
    """Transition not_processed → pending_for_approve."""
    return _transition_page(
        session,
        data_dir,
        slug=slug,
        expected="not_processed",
        new_status="pending_for_approve",
        change_kind="update",
        source=source,
        feedback=feedback,
    )


def approve_page(
    session: Session,
    data_dir: Path,
    *,
    slug: str,
    feedback: str = "",
    source: str = "console",
) -> dict:
    """Transition pending_for_approve → approved."""
    return _transition_page(
        session,
        data_dir,
        slug=slug,
        expected="pending_for_approve",
        new_status="approved",
        change_kind="approve",
        source=source,
        feedback=feedback,
        extra_fm={"approved_at": now_iso_kst()},
    )


def reject_page(
    session: Session,
    data_dir: Path,
    *,
    slug: str,
    feedback: str = "",
    source: str = "console",
) -> dict:
    """Reject a page from pending_for_approve or not_processed."""
    page = session.execute(select(Page).where(Page.slug == slug)).scalar_one_or_none()
    if page is None:
        raise ServiceError("not_found", "page not found")
    if page.review_status not in {"pending_for_approve", "not_processed"}:
        raise ServiceError(
            "conflict", f"reject not allowed from {page.review_status!r}"
        )

    old_status = page.review_status
    page.review_status = "rejected"
    if page.export_path and page.export_path.startswith("wiki/"):
        page.export_path = "rejected/" + page.export_path.removeprefix("wiki/")
    _sync_page_frontmatter(
        page,
        {
            "review_status": "rejected",
            "rejected_at": now_iso_kst(),
            "rejected_by": source,
        },
    )
    page.updated_at = now_iso_kst()
    _append_revision(
        session,
        page,
        change_kind="reject",
        changed_fields={"review_status": {"old": old_status, "new": "rejected"}},
        source=source,
        note=feedback or None,
    )
    return commit_and_export(session, data_dir, {"page": _page_payload(page)})


def ttl_sweep(session: Session, data_dir: Path, *, days: int = 7) -> dict:
    """Reject all not_processed pages older than ``days`` days."""
    today = today_kst()
    swept = 0
    for page in session.execute(
        select(Page).where(Page.review_status == "not_processed")
    ).scalars():
        created = str(page.frontmatter.get("created") or "")[:10]
        if not created:
            continue
        age = (date_from_iso(today) - date_from_iso(created)).days
        if age < days:
            continue
        old_status = page.review_status
        page.review_status = "rejected"
        if page.export_path and page.export_path.startswith("wiki/"):
            page.export_path = "rejected/" + page.export_path.removeprefix("wiki/")
        _sync_page_frontmatter(
            page,
            {
                "review_status": "rejected",
                "rejected_at": now_iso_kst(),
                "rejected_by": "auto_ttl",
            },
        )
        _append_revision(
            session,
            page,
            change_kind="reject",
            changed_fields={"review_status": {"old": old_status, "new": "rejected"}},
            source="system",
            note=f"No promotion within {days}d window.",
        )
        swept += 1
    return commit_and_export(session, data_dir, {"swept": swept})
