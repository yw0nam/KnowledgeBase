#!/usr/bin/env python3
"""Deterministic Hermes daily usage report generator."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from kb import REPO_ROOT as BASEDIR
from kb.cli.db_api import submit_markdown_page, submit_metrics
from kb.cli.usage_reports.collect import (
    DEFAULT_HERMES_DB,
    DEFERRED_METRICS,
    _collect_hermes,
    _pct,
)
from kb.cli.usage_reports.render import (
    _fmt,
    _hourly_lines,
    _int,
    _kv_lines,
    _model_table,
    _pct as _pct_text,
    _schema_cell,
)

KST = timezone(timedelta(hours=9))


def _summary_dir(base_dir: Path, target_date: str) -> Path:
    year, month, _ = target_date.split("-")
    return base_dir / "data/wiki/summaries" / year / month


def _metrics_dir(base_dir: Path, target_date: str) -> Path:
    year, month, _ = target_date.split("-")
    return base_dir / "data/ops/reports" / year / month


def collect_metrics(
    target_date: str, db_path: Path = DEFAULT_HERMES_DB
) -> dict[str, Any]:
    return {
        "date": target_date,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "deferred_metrics": DEFERRED_METRICS,
        "hermes": _collect_hermes(target_date, Path(db_path)),
        "policy_compliance": {
            "passed": 0,
            "total": 0,
            "rate_pct": None,
            "status": "not_evaluated_until_write",
        },
    }


def _observations(metrics: dict[str, Any]) -> list[str]:
    he = metrics["hermes"]
    if not he.get("available", True):
        return [f"Hermes DB unavailable: {he.get('reason')}"]
    obs: list[str] = []
    if float(he.get("sessions", {}).get("zombie") or 0) > 0:
        obs.append(
            f"Zombie sessions {_fmt(he.get('sessions', {}).get('zombie'))} found. Check TUI/cron shutdown handling."
        )
    if not obs:
        obs.append("No notable signals. Current values can be used as baseline.")
    return obs


def render_report(metrics: dict[str, Any]) -> str:
    d = metrics["date"]
    he = metrics["hermes"]
    pc = metrics["policy_compliance"]
    observations = "\n".join(f"- {line}" for line in _observations(metrics))
    return f"""---
type: summary
subtype: daily
date: "{d}"
created: "{d}"
updated: "{d}"
sources: []
tags: [agent-usage, deterministic-report, hermes]
---

# Hermes Daily Report - {d}

## Summary

- Root sessions: {_fmt(he.get('sessions', {}).get('root'))}
- Zombie sessions: {_fmt(he.get('sessions', {}).get('zombie'))}
- Turns: {_int(he.get('n_turns'))}
- Tool calls: {_int(he.get('n_toolcalls'))}
- Total tokens: {_int(he.get('tokens', {}).get('total'))}
- Recorded cost: {_fmt(he.get('cost', {}).get('recorded_usd'))} USD

## Development/Evaluation Metrics

| Metric | Hermes | Status |
|---|---:|---|
| Task Completion Rate | N/A | task schema needed |
| Error Rate | N/A | source schema needed |
| Hallucinated Parameters | {_schema_cell(he)} | deterministic where available |
| n_toolcalls / n_turns | {_fmt(he.get('n_toolcalls'))} / {_fmt(he.get('n_turns'))} | deterministic |
| Policy Compliance Rate | {_pct_text(pc.get('rate_pct'))} | {pc.get('status')} |

## Layer 1: Cost and Efficiency

- Tokens: {_int(he.get('tokens', {}).get('total'))} (input {_int(he.get('tokens', {}).get('input'))} / output {_int(he.get('tokens', {}).get('output'))} / cache_read {_int(he.get('tokens', {}).get('cache_read'))} / cache_write {_int(he.get('tokens', {}).get('cache_write'))} / reasoning {_int(he.get('tokens', {}).get('reasoning'))})
- Recorded cost: {_fmt(he.get('cost', {}).get('recorded_usd'))} USD
- Average session time: {_fmt(he.get('latency', {}).get('avg_session_sec'))}s / max {_fmt(he.get('latency', {}).get('max_session_sec'))}s
- Model usage:

{_model_table(he.get('model_usage', []), include_sessions=True)}

## Layer 2: Work Quality

- End reason distribution:
{_kv_lines(he.get('end_reason_distribution', []), 'end_reason')}
- Source distribution:
{_kv_lines(he.get('source_distribution', []), 'source')}
- Zombie sessions: {_fmt(he.get('sessions', {}).get('zombie'))}
- Hallucinated Parameters: {_schema_cell(he)}

## Layer 3: Behavior Pattern

- Hourly sessions (KST):
{_hourly_lines(he.get('hourly_sessions', []))}
- n_toolcalls / n_turns: {_fmt(he.get('n_toolcalls'))} / {_fmt(he.get('n_turns'))}

## Layer 4: Focus and Stability

- Model sessions:
{_kv_lines(he.get('model_usage', []), 'model')}
- Max session latency: {_fmt(he.get('latency', {}).get('max_session_sec'))}s

## Problems / Improvement Candidates

{observations}
"""


def _write_policy(report_path: Path, metrics_path: Path, report: str) -> dict[str, Any]:
    checks = [
        report_path.as_posix().endswith("-hermes-usage.md"),
        "/data/wiki/summaries/" in report_path.as_posix(),
        "/data/ops/reports/" in metrics_path.as_posix(),
        "sources: []" in report,
        "$" not in report,
    ]
    passed = sum(1 for c in checks if c)
    return {
        "passed": passed,
        "total": len(checks),
        "rate_pct": _pct(passed, len(checks)),
        "status": "evaluated",
    }


def write_outputs(
    metrics: dict[str, Any], base_dir: Path = BASEDIR
) -> dict[str, object]:
    d = metrics["date"]
    report_path = _summary_dir(base_dir, d) / f"{d}-hermes-usage.md"
    report = render_report(metrics)
    metrics["policy_compliance"] = _write_policy(report_path, report_path, report)
    report = render_report(metrics)
    export_path = report_path.relative_to(base_dir / "data").as_posix()
    submit_markdown_page(
        markdown=report,
        export_path=export_path,
        slug=report_path.stem,
        source="cli",
    )
    he = metrics.get("hermes", {})
    submit_metrics(
        report_date=d,
        report_type="hermes",
        metrics=metrics,
        token_total=_int_or_none(he.get("tokens", {}).get("total")),
        cost_usd=_float_or_none(he.get("cost", {}).get("recorded_usd")),
    )
    return {"report": report_path, "metrics": "db"}


def _int_or_none(val: Any) -> int | None:
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def _float_or_none(val: Any) -> float | None:
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _default_target_date() -> str:
    return (datetime.now(KST).date() - timedelta(days=1)).isoformat()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", default=_default_target_date())
    parser.add_argument("--hermes-db", type=Path, default=DEFAULT_HERMES_DB)
    parser.add_argument("--base-dir", type=Path, default=BASEDIR)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--lint", action="store_true")
    args = parser.parse_args(argv)

    metrics = collect_metrics(args.date, args.hermes_db)
    if args.dry_run:
        print(render_report(metrics))
        return 0
    outputs = write_outputs(metrics, args.base_dir)
    print("generated:")
    for key, path in outputs.items():
        print(f"- {key}: {path}")
    if args.lint:
        print("lint: skipped; DB API validates and exports Markdown on write")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
