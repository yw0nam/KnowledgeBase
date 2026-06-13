"""Markdown and JSON export from DB-canonical state."""

from __future__ import annotations

import json
from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from kb.db.models import (
    CronRun,
    ExportRecord,
    Handoff,
    MetricsRecord,
    OperationLog,
    Page,
    RawSource,
)
from kb.service._time import now_iso_kst


def _frontmatter_markdown(frontmatter: dict, body: str) -> str:
    block = yaml.safe_dump(
        frontmatter, sort_keys=False, allow_unicode=True, default_flow_style=False
    )
    if not body.startswith("\n"):
        body = "\n" + body
    return f"---\n{block}---{body}"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _clean_stale_markdown(data_dir: Path, expected: set[str]) -> int:
    """Remove .md files under wiki/ and handoffs/ not present in expected paths."""
    removed = 0
    for top in ("wiki", "rejected", "handoffs"):
        root = data_dir / top
        if not root.is_dir():
            continue
        for md in sorted(root.rglob("*.md"), reverse=True):
            rel = str(md.relative_to(data_dir))
            if rel in expected:
                continue
            md.unlink()
            removed += 1
    for top in ("wiki", "rejected", "handoffs"):
        root = data_dir / top
        if not root.is_dir():
            continue
        for d in sorted(root.rglob("*"), reverse=True):
            if d.is_dir() and not any(d.iterdir()):
                d.rmdir()
    return removed


def export_all(session: Session, data_dir: Path) -> int:
    """Export canonical DB rows to Markdown/JSON files.

    Export is derived output. Stale files that have no corresponding DB row
    are cleaned up automatically under wiki/, rejected/, and handoffs/.
    """
    written = 0
    expected: set[str] = set()

    for raw in session.execute(
        select(RawSource).order_by(RawSource.source_key)
    ).scalars():
        _write(
            data_dir / raw.source_key,
            _frontmatter_markdown(raw.frontmatter, raw.content_md),
        )
        expected.add(raw.source_key)
        written += 1

    for page in session.execute(select(Page).order_by(Page.export_path)).scalars():
        if page.export_path is None:
            continue
        _write(
            data_dir / page.export_path,
            _frontmatter_markdown(page.frontmatter, page.body_md),
        )
        expected.add(page.export_path)
        written += 1

    for handoff in session.execute(
        select(Handoff).order_by(Handoff.export_path)
    ).scalars():
        _write(
            data_dir / handoff.export_path,
            _frontmatter_markdown(handoff.frontmatter, handoff.body_md),
        )
        expected.add(handoff.export_path)
        written += 1

    for metrics in session.execute(
        select(MetricsRecord).order_by(
            MetricsRecord.report_date, MetricsRecord.report_type
        )
    ).scalars():
        year, month, _ = metrics.report_date.split("-")
        path_str = (
            f"ops/reports/{year}/{month}"
            f"/{metrics.report_date}-{metrics.report_type}-usage.metrics.json"
        )
        _write(
            data_dir / path_str,
            json.dumps(
                metrics.metrics_json, ensure_ascii=False, indent=2, sort_keys=True
            )
            + "\n",
        )
        expected.add(path_str)
        written += 1

    logs = list(
        session.execute(
            select(OperationLog).order_by(OperationLog.log_date, OperationLog.id)
        )
        .scalars()
        .all()
    )
    if logs:
        body = "\n".join(log.body_md.rstrip() for log in logs).rstrip() + "\n"
        _write(data_dir / "log.md", body)
        expected.add("log.md")
        written += 1

    for run in session.execute(
        select(CronRun).where(CronRun.log_path.is_not(None))
    ).scalars():
        if run.log_path:
            _write(data_dir / run.log_path, run.log_body)
            expected.add(run.log_path)
            written += 1

    cleaned = _clean_stale_markdown(data_dir, expected)

    msg = f"wrote {written} files, cleaned {cleaned} stale"
    session.add(
        ExportRecord(
            target="markdown",
            status="success",
            message=msg,
            exported_at=now_iso_kst(),
        )
    )
    session.commit()
    return written


def record_export_failure(session: Session, message: str) -> None:
    session.rollback()
    session.add(
        ExportRecord(
            target="markdown",
            status="failed",
            message=message,
            exported_at=now_iso_kst(),
        )
    )
    session.commit()
