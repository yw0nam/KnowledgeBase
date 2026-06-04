"""DB-canonical write endpoints.

These routes are the write surface for cron jobs, skills, and future UI flows.
All writes require ``Authorization: Bearer $KB_API_TOKEN`` and export Markdown
derived output immediately after the DB transaction lands.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from kb.db import get_session
from kb.db.models import (
    CronRun,
    Handoff,
    MetricsRecord,
    OperationLog,
    Page,
    PageRevision,
    PageSource,
    RawSource,
)
from kb.lint.handoff import validate_handoff_create
from kb.lint.wiki import validate_page_create
from kb.web._time import date_from_iso, now_iso_kst, today_kst
from kb.web.auth import require_bearer
from kb.web.export import export_all, record_export_failure

router = APIRouter(tags=["db-canonical"])


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


def _commit_export_or_500(session: Session, data_dir, response: dict) -> dict:
    session.commit()
    try:
        written = export_all(session, data_dir)
    except Exception as exc:  # noqa: BLE001
        record_export_failure(session, str(exc))
        response["export"] = {"status": "failed", "db_written": True, "error": str(exc)}
        raise HTTPException(status_code=500, detail=response)
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
    """Return {field: {old, new}} for page columns whose value changes."""
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


class RawSourceBody(BaseModel):
    source_key: str
    source_type: str
    content_md: str
    frontmatter: dict = Field(default_factory=dict)
    source_url: str | None = None
    title: str | None = None
    captured_at: str | None = None
    created_at: str | None = None


@router.post("/raw-sources")
def create_raw_source(
    body: RawSourceBody,
    request: Request,
    session: Session = Depends(get_session),
) -> dict:
    require_bearer(request)
    row = RawSource(
        source_key=body.source_key,
        source_type=body.source_type,
        source_url=body.source_url,
        title=body.title or _first_heading(body.content_md, body.source_key),
        content_md=body.content_md,
        frontmatter=body.frontmatter,
        captured_at=body.captured_at,
        created_at=body.created_at or now_iso_kst(),
    )
    session.add(row)
    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=409, detail="raw_source already exists"
        ) from exc
    return _commit_export_or_500(
        session,
        request.app.state.config.data_dir,
        {"id": row.id, "source_key": row.source_key},
    )


class PageCreateBody(BaseModel):
    slug: str
    type: Literal[
        "entity",
        "concept",
        "decision",
        "question",
        "improvement",
        "checklist",
        "summary",
    ]
    body_md: str
    frontmatter: dict
    title: str | None = None
    category: str | None = None
    review_status: str | None = None
    origin: str = "ingested"
    export_path: str
    created_at: str | None = None
    updated_at: str | None = None
    source: str = "agent"


@router.post("/pages")
def create_page(
    body: PageCreateBody,
    request: Request,
    session: Session = Depends(get_session),
) -> dict:
    require_bearer(request)
    now = now_iso_kst()
    review_status = body.review_status
    if review_status is None:
        review_status = body.frontmatter.get("review_status")
    title = (
        body.title
        or body.frontmatter.get("title")
        or _first_heading(body.body_md, body.slug)
    )
    category = body.category or body.frontmatter.get("category")

    lint_result = validate_page_create(
        body.frontmatter, body.body_md, session, slug=body.slug
    )
    if not lint_result.ok:
        raise HTTPException(
            status_code=422,
            detail={"errors": lint_result.errors, "warnings": lint_result.warnings},
        )

    fields = {
        "title": title,
        "type": body.type,
        "category": category,
        "review_status": review_status,
        "origin": body.origin,
        "body_md": body.body_md,
        "frontmatter": body.frontmatter,
        "export_path": body.export_path,
    }

    existing = session.execute(
        select(Page).where(Page.slug == body.slug)
    ).scalar_one_or_none()

    if existing is None:
        page = Page(
            slug=body.slug,
            created_at=body.created_at or now,
            updated_at=body.updated_at or now,
            **fields,
        )
        session.add(page)
        try:
            session.flush()
        except IntegrityError as exc:
            session.rollback()
            raise HTTPException(status_code=409, detail="page already exists") from exc
        _refresh_page_sources(session, page)
        _append_revision(
            session, page, change_kind="create", changed_fields=None, source=body.source
        )
        return _commit_export_or_500(
            session, request.app.state.config.data_dir, {"page": _page_payload(page)}
        )

    page = existing
    changed = _diff_page_fields(page, fields)
    for field, value in fields.items():
        setattr(page, field, value)
    page.updated_at = now
    _refresh_page_sources(session, page)
    _append_revision(
        session,
        page,
        change_kind="update",
        changed_fields=changed or None,
        source=body.source,
    )
    return _commit_export_or_500(
        session, request.app.state.config.data_dir, {"page": _page_payload(page)}
    )


class PagePatchBody(BaseModel):
    title: str | None = None
    body_md: str | None = None
    frontmatter: dict | None = None
    category: str | None = None
    review_status: str | None = None
    source: str = "agent"
    note: str | None = None


@router.patch("/pages/{slug}")
def patch_page(
    slug: str,
    body: PagePatchBody,
    request: Request,
    session: Session = Depends(get_session),
) -> dict:
    require_bearer(request)
    page = session.execute(select(Page).where(Page.slug == slug)).scalar_one_or_none()
    if page is None:
        raise HTTPException(status_code=404, detail="page not found")
    changed: dict[str, dict] = {}
    if body.title is not None and body.title != page.title:
        changed["title"] = {"old": page.title, "new": body.title}
        page.title = body.title
    if body.body_md is not None and body.body_md != page.body_md:
        changed["body_md"] = {"old": page.body_md, "new": body.body_md}
        page.body_md = body.body_md
    if body.frontmatter is not None and body.frontmatter != page.frontmatter:
        changed["frontmatter"] = {"old": page.frontmatter, "new": body.frontmatter}
        page.frontmatter = body.frontmatter
        if "category" in body.frontmatter:
            page.category = body.frontmatter.get("category")
        if "review_status" in body.frontmatter:
            page.review_status = body.frontmatter.get("review_status")
    if body.category is not None and body.category != page.category:
        changed["category"] = {"old": page.category, "new": body.category}
        page.category = body.category
        _sync_page_frontmatter(page, {"category": body.category})
    if body.review_status is not None and body.review_status != page.review_status:
        changed["review_status"] = {
            "old": page.review_status,
            "new": body.review_status,
        }
        page.review_status = body.review_status
        _sync_page_frontmatter(page, {"review_status": body.review_status})
    if not changed:
        return {"page": _page_payload(page), "export": {"status": "skipped"}}
    lint_result = validate_page_create(
        page.frontmatter, page.body_md, session, slug=page.slug
    )
    if not lint_result.ok:
        raise HTTPException(
            status_code=422,
            detail={"errors": lint_result.errors, "warnings": lint_result.warnings},
        )
    page.updated_at = now_iso_kst()
    _refresh_page_sources(session, page)
    _append_revision(
        session,
        page,
        change_kind="update",
        changed_fields=changed,
        source=body.source,
        note=body.note,
    )
    return _commit_export_or_500(
        session, request.app.state.config.data_dir, {"page": _page_payload(page)}
    )


class FeedbackBody(BaseModel):
    feedback: str = ""
    source: str = "console"


def _transition_page(
    slug: str,
    body: FeedbackBody,
    request: Request,
    session: Session,
    *,
    expected: str,
    new_status: str,
    change_kind: str,
    extra_fm: dict | None = None,
) -> dict:
    require_bearer(request)
    page = session.execute(select(Page).where(Page.slug == slug)).scalar_one_or_none()
    if page is None:
        raise HTTPException(status_code=404, detail="page not found")
    if page.review_status != expected:
        raise HTTPException(
            status_code=409,
            detail=f"expected {expected}, current {page.review_status!r}",
        )
    changed = {"review_status": {"old": page.review_status, "new": new_status}}
    page.review_status = new_status
    fields = {"review_status": new_status}
    if extra_fm:
        fields.update(extra_fm)
    _sync_page_frontmatter(page, fields)
    page.updated_at = now_iso_kst()
    _append_revision(
        session,
        page,
        change_kind=change_kind,
        changed_fields=changed,
        source=body.source,
        note=body.feedback or None,
    )
    return _commit_export_or_500(
        session, request.app.state.config.data_dir, {"page": _page_payload(page)}
    )


@router.post("/pages/{slug}/promote")
def promote_page(
    slug: str,
    body: FeedbackBody,
    request: Request,
    session: Session = Depends(get_session),
) -> dict:
    return _transition_page(
        slug,
        body,
        request,
        session,
        expected="not_processed",
        new_status="pending_for_approve",
        change_kind="update",
    )


@router.post("/pages/{slug}/approve")
def approve_page(
    slug: str,
    body: FeedbackBody,
    request: Request,
    session: Session = Depends(get_session),
) -> dict:
    return _transition_page(
        slug,
        body,
        request,
        session,
        expected="pending_for_approve",
        new_status="approved",
        change_kind="approve",
        extra_fm={"approved_at": now_iso_kst()},
    )


@router.post("/pages/{slug}/reject")
def reject_page(
    slug: str,
    body: FeedbackBody,
    request: Request,
    session: Session = Depends(get_session),
) -> dict:
    require_bearer(request)
    page = session.execute(select(Page).where(Page.slug == slug)).scalar_one_or_none()
    if page is None:
        raise HTTPException(status_code=404, detail="page not found")
    if page.review_status not in {"pending_for_approve", "not_processed"}:
        raise HTTPException(
            status_code=409,
            detail=f"reject not allowed from {page.review_status!r}",
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
            "rejected_by": body.source,
        },
    )
    page.updated_at = now_iso_kst()
    _append_revision(
        session,
        page,
        change_kind="reject",
        changed_fields={"review_status": {"old": old_status, "new": "rejected"}},
        source=body.source,
        note=body.feedback or None,
    )
    return _commit_export_or_500(
        session, request.app.state.config.data_dir, {"page": _page_payload(page)}
    )


@router.post("/pages/ttl-sweep")
def ttl_sweep(
    request: Request,
    days: int = 7,
    session: Session = Depends(get_session),
) -> dict:
    require_bearer(request)
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
    return _commit_export_or_500(
        session, request.app.state.config.data_dir, {"swept": swept}
    )


class HandoffBody(BaseModel):
    handoff_id: str
    task_slug: str
    role: str
    handoff_seq: int
    status: str
    frontmatter: dict
    body_md: str
    export_path: str
    subject: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


@router.post("/handoffs")
def create_handoff(
    body: HandoffBody,
    request: Request,
    session: Session = Depends(get_session),
) -> dict:
    require_bearer(request)
    now = now_iso_kst()
    row = Handoff(
        handoff_id=body.handoff_id,
        task_slug=body.task_slug,
        subject=body.subject,
        role=body.role,
        handoff_seq=body.handoff_seq,
        status=body.status,
        frontmatter=body.frontmatter,
        body_md=body.body_md,
        export_path=body.export_path,
        created_at=body.created_at or now,
        updated_at=body.updated_at or now,
    )
    lint_result = validate_handoff_create(body.frontmatter, body.body_md)
    if not lint_result.ok:
        raise HTTPException(
            status_code=422,
            detail={"errors": lint_result.errors, "warnings": lint_result.warnings},
        )
    session.add(row)
    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail="handoff already exists") from exc
    return _commit_export_or_500(
        session, request.app.state.config.data_dir, {"id": row.id}
    )


class OperationLogBody(BaseModel):
    log_date: str
    category: str
    body_md: str
    created_at: str | None = None


@router.post("/operation-logs")
def create_operation_log(
    body: OperationLogBody,
    request: Request,
    session: Session = Depends(get_session),
) -> dict:
    require_bearer(request)
    row = OperationLog(
        log_date=body.log_date,
        category=body.category,
        body_md=body.body_md,
        created_at=body.created_at or now_iso_kst(),
    )
    session.add(row)
    session.flush()
    return _commit_export_or_500(
        session, request.app.state.config.data_dir, {"id": row.id}
    )


class CronRunBody(BaseModel):
    job_name: str
    target: str
    status: str
    log_body: str
    exit_code: int | None = None
    log_path: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    created_at: str | None = None


@router.post("/cron-runs")
def create_cron_run(
    body: CronRunBody,
    request: Request,
    session: Session = Depends(get_session),
) -> dict:
    require_bearer(request)
    row = CronRun(
        job_name=body.job_name,
        target=body.target,
        status=body.status,
        exit_code=body.exit_code,
        log_body=body.log_body,
        log_path=body.log_path,
        started_at=body.started_at,
        finished_at=body.finished_at,
        created_at=body.created_at or now_iso_kst(),
    )
    session.add(row)
    session.flush()
    return _commit_export_or_500(
        session, request.app.state.config.data_dir, {"id": row.id}
    )


@router.post("/export/markdown")
def export_markdown(
    request: Request,
    session: Session = Depends(get_session),
) -> dict:
    require_bearer(request)
    try:
        written = export_all(session, request.app.state.config.data_dir)
    except Exception as exc:  # noqa: BLE001
        record_export_failure(session, str(exc))
        raise HTTPException(status_code=500, detail=str(exc))
    return {"status": "success", "written": written}


class MetricsBody(BaseModel):
    report_date: str
    report_type: str
    session_count: int | None = None
    token_total: int | None = None
    cost_usd: float | None = None
    tool_error_count: int | None = None
    metrics_json: dict


@router.post("/metrics")
def create_metrics(
    body: MetricsBody,
    request: Request,
    session: Session = Depends(get_session),
) -> dict:
    require_bearer(request)
    row = session.execute(
        select(MetricsRecord).where(
            MetricsRecord.report_date == body.report_date,
            MetricsRecord.report_type == body.report_type,
        )
    ).scalar_one_or_none()
    if row is None:
        row = MetricsRecord(
            report_date=body.report_date,
            report_type=body.report_type,
            created_at=now_iso_kst(),
        )
        session.add(row)
    row.session_count = body.session_count
    row.token_total = body.token_total
    row.cost_usd = body.cost_usd
    row.tool_error_count = body.tool_error_count
    row.metrics_json = body.metrics_json
    session.flush()
    return _commit_export_or_500(
        session, request.app.state.config.data_dir, {"id": row.id}
    )
