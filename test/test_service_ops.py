"""Tests for kb.service.ops — RED→GREEN TDD."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import select

from kb.db.models import CronRun, ExportRecord, MetricsRecord, OperationLog
from kb.service.errors import ServiceError

# --------------------------------------------------------------------------- #
# OperationLog tests                                                            #
# --------------------------------------------------------------------------- #


def test_create_operation_log_success(data_dir: Path, session) -> None:
    """create_operation_log writes DB row and exports to log.md."""
    from kb.service.ops import create_operation_log

    result = create_operation_log(
        session,
        data_dir,
        log_date="2026-06-04",
        category="migration",
        body_md="## 2026-06-04 (migration)\n\n- **done**: DB canonical write\n",
    )

    assert result["export"]["status"] == "success"
    assert "id" in result

    # DB row
    row = session.execute(select(OperationLog)).scalar_one()
    assert row.category == "migration"
    assert row.log_date == "2026-06-04"

    # On-disk export
    log_file = data_dir / "log.md"
    assert log_file.exists()
    assert "DB canonical write" in log_file.read_text()


def test_create_operation_log_with_created_at(data_dir: Path, session) -> None:
    """created_at is stored when provided."""
    from kb.service.ops import create_operation_log

    create_operation_log(
        session,
        data_dir,
        log_date="2026-06-04",
        category="migration",
        body_md="## 2026-06-04\n\nEntry.\n",
        created_at="2026-06-04T00:00:00+09:00",
    )

    row = session.execute(select(OperationLog)).scalar_one()
    assert row.created_at == "2026-06-04T00:00:00+09:00"


# --------------------------------------------------------------------------- #
# CronRun tests                                                                 #
# --------------------------------------------------------------------------- #


def test_create_cron_run_success(data_dir: Path, session) -> None:
    """create_cron_run writes DB row."""
    from kb.service.ops import create_cron_run

    result = create_cron_run(
        session,
        data_dir,
        job_name="kb-memory-daily",
        target="2026-06-04",
        status="success",
        log_body="All done.\n",
        exit_code=0,
    )

    assert result["export"]["status"] == "success"
    assert "id" in result

    row = session.execute(select(CronRun)).scalar_one()
    assert row.job_name == "kb-memory-daily"
    assert row.status == "success"
    assert row.exit_code == 0


def test_create_cron_run_with_log_path(data_dir: Path, session) -> None:
    """When log_path is set the log file is written under data_dir."""
    from kb.service.ops import create_cron_run

    log_path = "raw/ops/cron/2026/06/2026-06-04_kb-memory-daily.log"
    result = create_cron_run(
        session,
        data_dir,
        job_name="kb-memory-daily",
        target="2026-06-04",
        status="success",
        log_body="Log content here.\n",
        exit_code=0,
        log_path=log_path,
    )

    assert result["export"]["status"] == "success"

    log_file = data_dir / log_path
    assert log_file.exists()
    assert "Log content here." in log_file.read_text()


def test_create_cron_run_no_log_path(data_dir: Path, session) -> None:
    """When log_path is None the export still succeeds (no file written)."""
    from kb.service.ops import create_cron_run

    result = create_cron_run(
        session,
        data_dir,
        job_name="kb-wiki-promote",
        target="2026-06-04",
        status="success",
        log_body="Done.\n",
        log_path=None,
    )

    assert result["export"]["status"] == "success"
    row = session.execute(select(CronRun)).scalar_one()
    assert row.log_path is None


# --------------------------------------------------------------------------- #
# MetricsRecord tests                                                           #
# --------------------------------------------------------------------------- #


def test_upsert_metrics_creates_row(data_dir: Path, session) -> None:
    """First upsert creates a MetricsRecord and exports JSON file."""
    from kb.service.ops import upsert_metrics

    result = upsert_metrics(
        session,
        data_dir,
        report_date="2026-06-04",
        report_type="opencode",
        token_total=100,
        metrics_json={"token_total": 100},
    )

    assert result["export"]["status"] == "success"
    assert "id" in result

    rows = (
        session.execute(
            select(MetricsRecord).where(
                MetricsRecord.report_date == "2026-06-04",
                MetricsRecord.report_type == "opencode",
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert rows[0].token_total == 100

    exported = data_dir / "ops/reports/2026/06/2026-06-04-opencode-usage.metrics.json"
    assert json.loads(exported.read_text()) == {"token_total": 100}


def test_upsert_metrics_keeps_single_row_per_date_type(data_dir: Path, session) -> None:
    """Second upsert for same (date,type) updates values; still one DB row."""
    from kb.service.ops import upsert_metrics

    upsert_metrics(
        session,
        data_dir,
        report_date="2026-06-04",
        report_type="opencode",
        token_total=100,
        metrics_json={"token_total": 100},
    )

    upsert_metrics(
        session,
        data_dir,
        report_date="2026-06-04",
        report_type="opencode",
        token_total=250,
        metrics_json={"token_total": 250},
    )

    rows = (
        session.execute(
            select(MetricsRecord).where(
                MetricsRecord.report_date == "2026-06-04",
                MetricsRecord.report_type == "opencode",
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert rows[0].token_total == 250

    exported = data_dir / "ops/reports/2026/06/2026-06-04-opencode-usage.metrics.json"
    assert json.loads(exported.read_text()) == {"token_total": 250}


def test_upsert_metrics_update_nulls_omitted_field(data_dir: Path, session) -> None:
    """On update, omitting a scalar field (default None) clears it in the DB.

    Documents the deliberate full-overwrite semantics: callers send a complete
    payload, so an omitted field is interpreted as a NULL write.
    """
    from kb.service.ops import upsert_metrics

    upsert_metrics(
        session,
        data_dir,
        report_date="2026-06-04",
        report_type="opencode",
        token_total=100,
        metrics_json={"token_total": 100},
    )

    # Second upsert omits token_total (defaults to None) → clears the column.
    upsert_metrics(
        session,
        data_dir,
        report_date="2026-06-04",
        report_type="opencode",
        metrics_json={"note": "no token total this time"},
    )

    row = session.execute(
        select(MetricsRecord).where(
            MetricsRecord.report_date == "2026-06-04",
            MetricsRecord.report_type == "opencode",
        )
    ).scalar_one()
    assert row.token_total is None


def test_upsert_metrics_different_types_separate_rows(data_dir: Path, session) -> None:
    """Different report_type values create separate rows."""
    from kb.service.ops import upsert_metrics

    upsert_metrics(
        session,
        data_dir,
        report_date="2026-06-04",
        report_type="opencode",
        metrics_json={"token_total": 10},
    )
    upsert_metrics(
        session,
        data_dir,
        report_date="2026-06-04",
        report_type="hermes",
        metrics_json={"token_total": 20},
    )

    rows = session.execute(select(MetricsRecord)).scalars().all()
    assert len(rows) == 2


# --------------------------------------------------------------------------- #
# export_markdown tests                                                         #
# --------------------------------------------------------------------------- #


def test_export_markdown_returns_success(data_dir: Path, session) -> None:
    """export_markdown returns {"status": "success", "written": int}."""
    from kb.service.ops import export_markdown

    result = export_markdown(session, data_dir)

    assert result["status"] == "success"
    assert isinstance(result["written"], int)


def test_export_markdown_after_operation_log(data_dir: Path, session) -> None:
    """export_markdown triggers export of previously committed rows."""
    from kb.service.ops import create_operation_log, export_markdown

    create_operation_log(
        session,
        data_dir,
        log_date="2026-06-04",
        category="test",
        body_md="## 2026-06-04 (test)\n\n- entry\n",
    )

    # Call export again to confirm idempotent
    result = export_markdown(session, data_dir)
    assert result["status"] == "success"
    assert result["written"] >= 1


def test_export_markdown_records_failure_and_raises(
    data_dir: Path, session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """On export failure, records an ExportRecord and raises export_failed.

    Fault injection: force export_all to raise, then verify the error path
    records the failure and surfaces ServiceError("export_failed", ...).
    """
    from kb.service.ops import export_markdown

    monkeypatch.setattr(
        "kb.service.ops.export_all",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    with pytest.raises(ServiceError) as exc_info:
        export_markdown(session, data_dir)

    assert exc_info.value.code == "export_failed"

    failed = (
        session.execute(select(ExportRecord).where(ExportRecord.status == "failed"))
        .scalars()
        .all()
    )
    assert len(failed) >= 1
