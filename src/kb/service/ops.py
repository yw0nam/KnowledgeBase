"""Service functions for operational records (OperationLog, CronRun, MetricsRecord).

Extracted from ``kb.web.routes.db_canonical`` route handlers with HTTP
specifics removed. HTTP exceptions become ``ServiceError``; ``data_dir``
replaces ``request.app.state.config.data_dir``.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from kb.db.models import CronRun, MetricsRecord, OperationLog
from kb.service._helpers import commit_and_export
from kb.service._time import now_iso_kst
from kb.service.errors import ServiceError
from kb.service.export import export_all, record_export_failure


def create_operation_log(
    session: Session,
    data_dir: Path,
    *,
    log_date: str,
    category: str,
    body_md: str,
    created_at: str | None = None,
) -> dict:
    """Insert an OperationLog row and export."""
    row = OperationLog(
        log_date=log_date,
        category=category,
        body_md=body_md,
        created_at=created_at or now_iso_kst(),
    )
    session.add(row)
    session.flush()
    return commit_and_export(session, data_dir, {"id": row.id})


def create_cron_run(
    session: Session,
    data_dir: Path,
    *,
    job_name: str,
    target: str,
    status: str,
    log_body: str,
    exit_code: int | None = None,
    log_path: str | None = None,
    started_at: str | None = None,
    finished_at: str | None = None,
    created_at: str | None = None,
) -> dict:
    """Insert a CronRun row and export."""
    row = CronRun(
        job_name=job_name,
        target=target,
        status=status,
        exit_code=exit_code,
        log_body=log_body,
        log_path=log_path,
        started_at=started_at,
        finished_at=finished_at,
        created_at=created_at or now_iso_kst(),
    )
    session.add(row)
    session.flush()
    return commit_and_export(session, data_dir, {"id": row.id})


def upsert_metrics(
    session: Session,
    data_dir: Path,
    *,
    report_date: str,
    report_type: str,
    metrics_json: dict,
    session_count: int | None = None,
    token_total: int | None = None,
    cost_usd: float | None = None,
    tool_error_count: int | None = None,
) -> dict:
    """Insert or update a MetricsRecord for (report_date, report_type).

    If a row already exists for the given (report_date, report_type) pair it is
    updated in place; otherwise a new row is created.  Latest values always win.
    """
    row = session.execute(
        select(MetricsRecord).where(
            MetricsRecord.report_date == report_date,
            MetricsRecord.report_type == report_type,
        )
    ).scalar_one_or_none()
    if row is None:
        row = MetricsRecord(
            report_date=report_date,
            report_type=report_type,
            created_at=now_iso_kst(),
        )
        session.add(row)
    row.session_count = session_count
    row.token_total = token_total
    row.cost_usd = cost_usd
    row.tool_error_count = tool_error_count
    row.metrics_json = metrics_json
    session.flush()
    return commit_and_export(session, data_dir, {"id": row.id})


def export_markdown(session: Session, data_dir: Path) -> dict:
    """Export all canonical DB rows to Markdown/JSON files.

    Returns ``{"status": "success", "written": int}``.
    Raises ``ServiceError("export_failed", ...)`` on failure after recording
    the failure in the DB.
    """
    try:
        written = export_all(session, data_dir)
    except Exception as exc:  # noqa: BLE001
        record_export_failure(session, str(exc))
        raise ServiceError("export_failed", str(exc))
    return {"status": "success", "written": written}
