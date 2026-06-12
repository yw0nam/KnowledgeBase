"""Shared in-process submit helper for the daily report CLIs.

Replaces the HTTP ``submit_markdown_page`` + ``submit_metrics`` pair with a
single in-process transaction via the service layer.
"""

from __future__ import annotations

from typing import Any

from kb.cli._payloads import markdown_page_payload
from kb.service import ops as service_ops
from kb.service import pages as service_pages
from kb.service.session import session_scope


def submit_page_and_metrics(
    *,
    report: str,
    export_path: str,
    slug: str,
    report_date: str,
    report_type: str,
    metrics: dict[str, Any],
    **metric_fields: Any,
) -> None:
    """Upsert the rendered report page + its metrics in one session scope.

    Two internal commits share the session (the page is committed before the
    metrics), so this is not a single atomic transaction.
    """
    payload = markdown_page_payload(
        markdown=report,
        export_path=export_path,
        slug=slug,
        origin="ingested",
        source="cli",
    )
    with session_scope() as (session, data_dir):
        service_pages.upsert_page(session, data_dir, **payload)
        service_ops.upsert_metrics(
            session,
            data_dir,
            report_date=report_date,
            report_type=report_type,
            metrics_json=metrics,
            **metric_fields,
        )
