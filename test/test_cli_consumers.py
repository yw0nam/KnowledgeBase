"""Integration tests for Task 8 CLI consumers — in-process service calls.

All tests use the real Postgres DB (via `database_url` + `session` fixtures) and
a temp `data_dir`.  The fixtures set DATABASE_URL and KB_DATA_DIR so that
session_scope() and service functions resolve them correctly.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import select

from kb.db.models import CronRun, MetricsRecord, Page
from kb.service import pages as service_pages

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SUMMARY_MD = """\
---
type: summary
subtype: daily
date: "2026-06-04"
created: "2026-06-04"
updated: "2026-06-04"
sources: []
tags: [agent-usage, deterministic-report, opencode]
---

# OpenCode Daily Report - 2026-06-04

## Summary

- Sessions: total 1

## Problems / Improvement Candidates

- No notable signals. Current values can be used as baseline.
"""


# ---------------------------------------------------------------------------
# submit_page_and_metrics
# ---------------------------------------------------------------------------


def test_submit_page_and_metrics_creates_page_and_metrics(
    database_url: str, data_dir: Path
) -> None:
    from kb.cli._submit import submit_page_and_metrics

    submit_page_and_metrics(
        report=_SUMMARY_MD,
        export_path="wiki/summaries/2026/06/2026-06-04-x-usage.md",
        slug="2026-06-04-x-usage",
        report_date="2026-06-04",
        report_type="opencode",
        metrics={"k": 1},
        token_total=5,
    )

    # Assert via a fresh session that the DB rows exist.
    from kb.db import make_engine, make_session_factory

    engine = make_engine()
    factory = make_session_factory(engine)
    sess = factory()
    try:
        page = sess.execute(
            select(Page).where(Page.slug == "2026-06-04-x-usage")
        ).scalar_one()
        assert page.slug == "2026-06-04-x-usage"

        metrics_row = sess.execute(
            select(MetricsRecord).where(
                MetricsRecord.report_date == "2026-06-04",
                MetricsRecord.report_type == "opencode",
            )
        ).scalar_one()
        assert metrics_row.token_total == 5
    finally:
        sess.close()
        engine.dispose()

    # Assert the export file exists on disk.
    export_file = data_dir / "wiki/summaries/2026/06/2026-06-04-x-usage.md"
    assert export_file.exists(), f"Export file not found: {export_file}"


# ---------------------------------------------------------------------------
# db_ttl_sweep.main
# ---------------------------------------------------------------------------


def test_db_ttl_sweep_main_rejects_stale_page(
    database_url: str, data_dir: Path
) -> None:
    import kb.cli.db_ttl_sweep as ttl_mod

    # Create a stale not_processed page via the service layer (same session scope).
    from kb.db import make_engine, make_session_factory

    engine = make_engine()
    factory = make_session_factory(engine)
    sess = factory()
    try:
        stale_fm = {
            "type": "concept",
            "review_status": "not_processed",
            "created": "2026-01-01",
            "updated": "2026-01-01",
            "sources": [],
            "tags": ["stale"],
        }
        service_pages.upsert_page(
            sess,
            data_dir,
            slug="stale-sweep-page",
            type="concept",
            body_md="\n# Stale Sweep Page\n\nA stale not_processed concept for CLI sweep test.\n",
            frontmatter=stale_fm,
            export_path="wiki/concepts/stale-sweep-page.md",
        )
    finally:
        sess.close()
        engine.dispose()

    # Call the CLI main — it uses session_scope() which reads DATABASE_URL / KB_DATA_DIR.
    rc = ttl_mod.main(["--days", "7"])
    assert rc == 0

    # Verify the page is now rejected in DB.
    engine2 = make_engine()
    factory2 = make_session_factory(engine2)
    sess2 = factory2()
    try:
        page = sess2.execute(
            select(Page).where(Page.slug == "stale-sweep-page")
        ).scalar_one()
        assert page.review_status == "rejected"
    finally:
        sess2.close()
        engine2.dispose()


# ---------------------------------------------------------------------------
# submit_cron_run.main
# ---------------------------------------------------------------------------


def test_submit_cron_run_main_creates_cron_run_row(
    database_url: str, data_dir: Path, tmp_path: Path
) -> None:
    import kb.cli.submit_cron_run as scr_mod

    logfile = tmp_path / "test.log"
    logfile.write_text("log line 1\nlog line 2\n", encoding="utf-8")

    rc = scr_mod.main(
        [
            "--job-name",
            "x",
            "--target",
            "y",
            "--status",
            "success",
            "--exit-code",
            "0",
            "--log-file",
            str(logfile),
        ]
    )
    assert rc == 0

    from kb.db import make_engine, make_session_factory

    engine = make_engine()
    factory = make_session_factory(engine)
    sess = factory()
    try:
        row = sess.execute(select(CronRun).where(CronRun.job_name == "x")).scalar_one()
        assert row.job_name == "x"
        assert row.target == "y"
        assert row.status == "success"
        assert row.exit_code == 0
    finally:
        sess.close()
        engine.dispose()
