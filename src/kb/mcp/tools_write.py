"""MCP write tools — one @mcp.tool per service write function.

Every tool follows the same pattern:
  1. Validate required args with ``require()`` → return error dict if missing.
  2. Open session via ``tool_session(ctx)`` from lifespan context.
  3. Call the corresponding service function.
  4. Catch ``ServiceError`` → return ``{"error", "code", "detail"}`` dict.

Tools never raise; they always return a plain dict.

Error shapes
------------
* Validation failure (missing required arg):
  ``{"error": <Korean message>, "code": "missing_args", "detail": [<field>, ...]}``
* Service failure (ServiceError):
  ``{"error": <str>, "code": <code>, "detail": <any>}``
  where ``code`` is one of: ``not_found``, ``conflict``, ``lint_failed``,
  ``export_failed``.

Callers can branch on ``result.get("code")`` to distinguish error types.
"""

from __future__ import annotations

from fastmcp import Context

from kb.mcp._session import tool_session
from kb.mcp.server import mcp
from kb.mcp.validators import NullableInt, NullableStr, require
from kb.service import handoffs as service_handoffs
from kb.service import ops as service_ops
from kb.service import pages as service_pages
from kb.service import sources as service_sources
from kb.service.errors import ServiceError

# ---------------------------------------------------------------------------
# Raw sources
# ---------------------------------------------------------------------------


@mcp.tool
def create_raw_source(
    ctx: Context,
    source_key: NullableStr = None,
    source_type: NullableStr = None,
    content_md: NullableStr = None,
    frontmatter: dict | None = None,
    source_url: NullableStr = None,
    title: NullableStr = None,
    captured_at: NullableStr = None,
    created_at: NullableStr = None,
) -> dict:
    """Ingest a raw source: insert a RawSource row and export to Markdown.

    Required: source_key (unique path key), source_type (e.g. "manual",
    "github", "web"), content_md (full Markdown body).
    Optional: frontmatter dict, source_url, title, captured_at, created_at (ISO).
    Raises conflict if source_key already exists.
    """
    missing = require(
        source_key=source_key, source_type=source_type, content_md=content_md
    )
    if missing:
        return missing
    try:
        with tool_session(ctx) as (session, data_dir):
            return service_sources.create_raw_source(
                session,
                data_dir,
                source_key=source_key,
                source_type=source_type,
                content_md=content_md,
                frontmatter=frontmatter,
                source_url=source_url,
                title=title,
                captured_at=captured_at,
                created_at=created_at,
            )
    except ServiceError as exc:
        return {"error": str(exc), "code": exc.code, "detail": exc.detail}


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------


@mcp.tool
def upsert_page(
    ctx: Context,
    slug: NullableStr = None,
    type: NullableStr = None,
    body_md: NullableStr = None,
    frontmatter: dict | None = None,
    export_path: NullableStr = None,
    title: NullableStr = None,
    category: NullableStr = None,
    review_status: NullableStr = None,
    origin: str = "ingested",
    created_at: NullableStr = None,
    updated_at: NullableStr = None,
    source: str = "agent",
) -> dict:
    """Create or update a wiki page (lint → DB → Markdown export).

    Required: slug (unique page identifier), type (e.g. "concept", "summary"),
    body_md (Markdown content), frontmatter (dict with at minimum type, created,
    updated, sources, tags fields), export_path (relative path under data/).
    Optional: title, category, review_status, origin, created_at, updated_at, source.
    Returns export status dict; raises lint_failed or conflict on validation errors.
    """
    missing = require(
        slug=slug,
        type=type,
        body_md=body_md,
        frontmatter=frontmatter,
        export_path=export_path,
    )
    if missing:
        return missing
    try:
        with tool_session(ctx) as (session, data_dir):
            return service_pages.upsert_page(
                session,
                data_dir,
                slug=slug,
                type=type,
                body_md=body_md,
                frontmatter=frontmatter,
                export_path=export_path,
                title=title,
                category=category,
                review_status=review_status,
                origin=origin,
                created_at=created_at,
                updated_at=updated_at,
                source=source,
            )
    except ServiceError as exc:
        return {"error": str(exc), "code": exc.code, "detail": exc.detail}


@mcp.tool
def patch_page(
    ctx: Context,
    slug: NullableStr = None,
    title: NullableStr = None,
    body_md: NullableStr = None,
    frontmatter: dict | None = None,
    category: NullableStr = None,
    review_status: NullableStr = None,
    source: str = "agent",
    note: NullableStr = None,
) -> dict:
    """Partially update an existing wiki page (only provided fields are changed).

    Required: slug (page to update).
    Optional: title, body_md, frontmatter, category, review_status, source, note.
    Returns export status dict; raises not_found if slug doesn't exist.
    """
    missing = require(slug=slug)
    if missing:
        return missing
    try:
        with tool_session(ctx) as (session, data_dir):
            return service_pages.patch_page(
                session,
                data_dir,
                slug=slug,
                title=title,
                body_md=body_md,
                frontmatter=frontmatter,
                category=category,
                review_status=review_status,
                source=source,
                note=note,
            )
    except ServiceError as exc:
        return {"error": str(exc), "code": exc.code, "detail": exc.detail}


@mcp.tool
def promote_page(
    ctx: Context,
    slug: NullableStr = None,
    feedback: str = "",
    source: str = "console",
) -> dict:
    """Advance a wiki page from not_processed → pending_for_approve.

    Required: slug. Optional: feedback (review notes), source.
    Returns updated page dict; raises conflict if page is not in not_processed state.
    """
    missing = require(slug=slug)
    if missing:
        return missing
    try:
        with tool_session(ctx) as (session, data_dir):
            return service_pages.promote_page(
                session, data_dir, slug=slug, feedback=feedback, source=source
            )
    except ServiceError as exc:
        return {"error": str(exc), "code": exc.code, "detail": exc.detail}


@mcp.tool
def approve_page(
    ctx: Context,
    slug: NullableStr = None,
    feedback: str = "",
    source: str = "console",
) -> dict:
    """Approve a wiki page (pending_for_approve → approved).

    Required: slug. Optional: feedback (review notes), source.
    Returns updated page dict; raises conflict if page is not in pending_for_approve state.
    """
    missing = require(slug=slug)
    if missing:
        return missing
    try:
        with tool_session(ctx) as (session, data_dir):
            return service_pages.approve_page(
                session, data_dir, slug=slug, feedback=feedback, source=source
            )
    except ServiceError as exc:
        return {"error": str(exc), "code": exc.code, "detail": exc.detail}


@mcp.tool
def reject_page(
    ctx: Context,
    slug: NullableStr = None,
    feedback: str = "",
    source: str = "console",
) -> dict:
    """Reject a wiki page (pending_for_approve or not_processed → rejected).

    Required: slug. Optional: feedback (rejection reason), source.
    Returns the updated page dict with export_path rewritten under rejected/.
    Raises a conflict error if the page is already approved or rejected.
    """
    missing = require(slug=slug)
    if missing:
        return missing
    try:
        with tool_session(ctx) as (session, data_dir):
            return service_pages.reject_page(
                session, data_dir, slug=slug, feedback=feedback, source=source
            )
    except ServiceError as exc:
        return {"error": str(exc), "code": exc.code, "detail": exc.detail}


@mcp.tool
def ttl_sweep_pages(
    ctx: Context,
    days: NullableInt = None,
) -> dict:
    """Reject all not_processed pages older than `days` days (default 7).

    Pass days=None or omit to use the 7-day default.
    Returns ``{"swept": int}`` with the number of pages rejected.
    """
    try:
        with tool_session(ctx) as (session, data_dir):
            return service_pages.ttl_sweep(
                session, data_dir, days=days if days is not None else 7
            )
    except ServiceError as exc:
        return {"error": str(exc), "code": exc.code, "detail": exc.detail}


# ---------------------------------------------------------------------------
# Handoffs
# ---------------------------------------------------------------------------


@mcp.tool
def create_handoff(
    ctx: Context,
    handoff_id: NullableStr = None,
    task_slug: NullableStr = None,
    role: NullableStr = None,
    handoff_seq: NullableInt = None,
    status: NullableStr = None,
    frontmatter: dict | None = None,
    body_md: NullableStr = None,
    export_path: NullableStr = None,
    subject: NullableStr = None,
    created_at: NullableStr = None,
    updated_at: NullableStr = None,
) -> dict:
    """Create a handoff document (lint → DB → Markdown export).

    Required: handoff_id (unique ID), task_slug, role (e.g. "agent"),
    handoff_seq (sequence number), status (e.g. "active", "completed"),
    frontmatter (dict), body_md, export_path.
    Optional: subject, created_at, updated_at.
    Raises lint_failed if frontmatter/body fails validation; conflict on duplicate id.
    """
    missing = require(
        handoff_id=handoff_id,
        task_slug=task_slug,
        role=role,
        handoff_seq=handoff_seq,
        status=status,
        frontmatter=frontmatter,
        body_md=body_md,
        export_path=export_path,
    )
    if missing:
        return missing
    try:
        with tool_session(ctx) as (session, data_dir):
            return service_handoffs.create_handoff(
                session,
                data_dir,
                handoff_id=handoff_id,
                task_slug=task_slug,
                role=role,
                handoff_seq=handoff_seq,
                status=status,
                frontmatter=frontmatter,
                body_md=body_md,
                export_path=export_path,
                subject=subject,
                created_at=created_at,
                updated_at=updated_at,
            )
    except ServiceError as exc:
        return {"error": str(exc), "code": exc.code, "detail": exc.detail}


# ---------------------------------------------------------------------------
# Operational records
# ---------------------------------------------------------------------------


@mcp.tool
def create_operation_log(
    ctx: Context,
    log_date: NullableStr = None,
    category: NullableStr = None,
    body_md: NullableStr = None,
    created_at: NullableStr = None,
) -> dict:
    """Insert an OperationLog entry and export to Markdown.

    Required: log_date (ISO date string, e.g. "2026-06-12"), category
    (e.g. "wiki", "handoff", "cron"), body_md (Markdown content).
    Optional: created_at.
    """
    missing = require(log_date=log_date, category=category, body_md=body_md)
    if missing:
        return missing
    try:
        with tool_session(ctx) as (session, data_dir):
            return service_ops.create_operation_log(
                session,
                data_dir,
                log_date=log_date,
                category=category,
                body_md=body_md,
                created_at=created_at,
            )
    except ServiceError as exc:
        return {"error": str(exc), "code": exc.code, "detail": exc.detail}


@mcp.tool
def create_cron_run(
    ctx: Context,
    job_name: NullableStr = None,
    target: NullableStr = None,
    status: NullableStr = None,
    log_body: NullableStr = None,
    exit_code: NullableInt = None,
    log_path: NullableStr = None,
    started_at: NullableStr = None,
    finished_at: NullableStr = None,
    created_at: NullableStr = None,
) -> dict:
    """Record a cron job execution and export to Markdown.

    Required: job_name (e.g. "kb-memory-daily"), target (date or identifier,
    e.g. "2026-06-12"), status (e.g. "success", "failed"), log_body (log content).
    Optional: exit_code, log_path, started_at, finished_at (ISO), created_at.
    """
    missing = require(
        job_name=job_name, target=target, status=status, log_body=log_body
    )
    if missing:
        return missing
    try:
        with tool_session(ctx) as (session, data_dir):
            return service_ops.create_cron_run(
                session,
                data_dir,
                job_name=job_name,
                target=target,
                status=status,
                log_body=log_body,
                exit_code=exit_code,
                log_path=log_path,
                started_at=started_at,
                finished_at=finished_at,
                created_at=created_at,
            )
    except ServiceError as exc:
        return {"error": str(exc), "code": exc.code, "detail": exc.detail}


@mcp.tool
def upsert_metrics(
    ctx: Context,
    report_date: NullableStr = None,
    report_type: NullableStr = None,
    metrics_json: dict | None = None,
    session_count: NullableInt = None,
    token_total: NullableInt = None,
    cost_usd: float | None = None,
    tool_error_count: NullableInt = None,
) -> dict:
    """Insert or update a MetricsRecord for (report_date, report_type).

    Required: report_date (ISO date, e.g. "2026-06-12"), report_type
    (e.g. "opencode", "hermes", "claude_code"), metrics_json (raw metrics dict).
    Optional: session_count, token_total, cost_usd, tool_error_count.
    If a row already exists for the (report_date, report_type) pair it is updated.
    """
    missing = require(
        report_date=report_date,
        report_type=report_type,
        metrics_json=metrics_json,
    )
    if missing:
        return missing
    try:
        with tool_session(ctx) as (session, data_dir):
            return service_ops.upsert_metrics(
                session,
                data_dir,
                report_date=report_date,
                report_type=report_type,
                metrics_json=metrics_json,
                session_count=session_count,
                token_total=token_total,
                cost_usd=cost_usd,
                tool_error_count=tool_error_count,
            )
    except ServiceError as exc:
        return {"error": str(exc), "code": exc.code, "detail": exc.detail}


@mcp.tool
def export_markdown(ctx: Context) -> dict:
    """Export all canonical DB rows to Markdown/JSON files under data_dir.

    No required args. Returns ``{"status": "success", "written": int}``.
    Raises export_failed if any file write fails.
    """
    try:
        with tool_session(ctx) as (session, data_dir):
            return service_ops.export_markdown(session, data_dir)
    except ServiceError as exc:
        return {"error": str(exc), "code": exc.code, "detail": exc.detail}
