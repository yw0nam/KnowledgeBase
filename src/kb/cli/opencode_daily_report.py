#!/usr/bin/env python3
"""Deterministic OpenCode daily usage report generator."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from kb import REPO_ROOT as BASEDIR
from kb.cli._submit import submit_page_and_metrics
from kb.cli.usage_reports.collect import (
    DEFAULT_OPENCODE_DB,
    DEFERRED_METRICS,
    _collect_opencode,
    _pct,
)
from kb.cli.usage_reports.render import (
    _fmt,
    _hot_files,
    _hourly_lines,
    _int,
    _model_table,
    _pct as _pct_text,
    _schema_cell,
    _tool_table,
)

KST = timezone(timedelta(hours=9))


def _summary_dir(base_dir: Path, target_date: str) -> Path:
    year, month, _ = target_date.split("-")
    return base_dir / "data/wiki/summaries" / year / month


def _metrics_dir(base_dir: Path, target_date: str) -> Path:
    year, month, _ = target_date.split("-")
    return base_dir / "data/ops/reports" / year / month


def collect_metrics(
    target_date: str, db_path: Path = DEFAULT_OPENCODE_DB
) -> dict[str, Any]:
    return {
        "date": target_date,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "deferred_metrics": DEFERRED_METRICS,
        "opencode": _collect_opencode(target_date, Path(db_path)),
        "policy_compliance": {
            "passed": 0,
            "total": 0,
            "rate_pct": None,
            "status": "not_evaluated_until_write",
        },
    }


def _observations(metrics: dict[str, Any]) -> list[str]:
    oc = metrics["opencode"]
    obs: list[str] = []
    if not oc.get("available", True):
        return [f"OpenCode DB unavailable: {oc.get('reason')}"]
    cache_models = [
        r for r in oc.get("model_usage", []) if float(r.get("cache_hit_pct") or 0) >= 95
    ]
    if cache_models:
        names = ", ".join(str(r.get("model")) for r in cache_models[:3])
        obs.append(
            f"High cache-hit models detected ({names}); this suggests repeated-context work patterns."
        )
    todo = oc.get("todo", {})
    if todo.get("total"):
        obs.append(
            f"TODO completion rate is {_pct_text(todo.get('completion_rate_pct'))} ({_fmt(todo.get('completed'))}/{_fmt(todo.get('total'))})."
        )
    errors = [
        r for r in oc.get("tool_breakdown", []) if float(r.get("errors") or 0) > 0
    ]
    if errors:
        worst = sorted(
            errors,
            key=lambda r: (
                float(r.get("error_rate_pct") or 0),
                float(r.get("errors") or 0),
            ),
            reverse=True,
        )[0]
        obs.append(
            f"Tool errors are most visible in {worst.get('tool')}: {_fmt(worst.get('errors'))}/{_fmt(worst.get('calls'))} ({_pct_text(worst.get('error_rate_pct'))})."
        )
    if not obs:
        obs.append("No notable signals. Current values can be used as baseline.")
    return obs


def render_report(metrics: dict[str, Any]) -> str:
    d = metrics["date"]
    oc = metrics["opencode"]
    pc = metrics["policy_compliance"]
    todo = oc.get("todo", {})
    delegation_rate = None
    if float(oc.get("sessions", {}).get("total") or 0):
        delegation_rate = round(
            float(oc.get("sessions", {}).get("subagent") or 0)
            * 100
            / float(oc.get("sessions", {}).get("total") or 0),
            2,
        )
    observations = "\n".join(f"- {line}" for line in _observations(metrics))
    return f"""---
type: summary
subtype: daily
date: "{d}"
created: "{d}"
updated: "{d}"
sources: []
tags: [agent-usage, deterministic-report, opencode]
---

# OpenCode Daily Report - {d}

## Summary

- Sessions: total {_fmt(oc.get('sessions', {}).get('total'))} (root {_fmt(oc.get('sessions', {}).get('root'))} / subagent {_fmt(oc.get('sessions', {}).get('subagent'))})
- Projects: {_fmt(oc.get('sessions', {}).get('projects'))}
- Total tokens: {_int(oc.get('tokens', {}).get('total'))}
- Recorded cost: {_fmt(oc.get('cost', {}).get('recorded_usd'))} USD
- TODO completion: {_pct_text(todo.get('completion_rate_pct'))} ({_fmt(todo.get('completed'))}/{_fmt(todo.get('total'))})
- Delegation rate: {_pct_text(delegation_rate)}

## Development/Evaluation Metrics

| Metric | OpenCode | Status |
|---|---:|---|
| Task Completion Rate | TODO proxy {_pct_text(todo.get('completion_rate_pct'))} ({_fmt(todo.get('completed'))}/{_fmt(todo.get('total'))}) | task schema needed for true eval |
| Error Rate | {_fmt(oc.get('error_rate', {}).get('tool_errors'))}/{_fmt(oc.get('error_rate', {}).get('tool_calls'))} ({_fmt(oc.get('error_rate', {}).get('rate_pct'))}%) | deterministic |
| Hallucinated Parameters | {_schema_cell(oc)} | deterministic schema check |
| n_toolcalls / n_turns | {_fmt(oc.get('n_toolcalls'))} / {_fmt(oc.get('n_turns'))} | deterministic |
| Policy Compliance Rate | {_pct_text(pc.get('rate_pct'))} | {pc.get('status')} |

## Layer 1: Cost and Efficiency

- Tokens: {_int(oc.get('tokens', {}).get('total'))} (input {_int(oc.get('tokens', {}).get('input'))} / output {_int(oc.get('tokens', {}).get('output'))} / cache_read {_int(oc.get('tokens', {}).get('cache_read'))} / cache_write {_int(oc.get('tokens', {}).get('cache_write'))} / reasoning {_int(oc.get('tokens', {}).get('reasoning'))})
- Recorded cost: {_fmt(oc.get('cost', {}).get('recorded_usd'))} USD
- Average session time: {_fmt(oc.get('latency', {}).get('avg_session_sec'))}s / max {_fmt(oc.get('latency', {}).get('max_session_sec'))}s
- Model usage:

{_model_table(oc.get('model_usage', []))}

## Layer 2: Work Quality

- TODO completion: {_pct_text(todo.get('completion_rate_pct'))} ({_fmt(todo.get('completed'))}/{_fmt(todo.get('total'))})
- Tool error rate: {_fmt(oc.get('error_rate', {}).get('rate_pct'))}% ({_fmt(oc.get('error_rate', {}).get('tool_errors'))}/{_fmt(oc.get('error_rate', {}).get('tool_calls'))})
- Tool errors:

{_tool_table(oc.get('tool_breakdown', []))}

- Hallucinated Parameters: {_schema_cell(oc)}
- Compactions: {_fmt(oc.get('sessions', {}).get('compactions'))}

## Layer 3: Behavior Pattern

- Hourly sessions (KST):
{_hourly_lines(oc.get('hourly_sessions', []))}
- root vs subagent: root {_fmt(oc.get('sessions', {}).get('root'))} / subagent {_fmt(oc.get('sessions', {}).get('subagent'))}

## Layer 4: Focus and Stability

- Project distribution:
{chr(10).join(f"  - {r.get('project')}: {_fmt(r.get('sessions'))}" for r in oc.get('projects', [])[:8]) or '  - N/A'}
- Hot files:
{_hot_files(oc.get('hot_files', []))}

## Problems / Improvement Candidates

{observations}
"""


def _write_policy(report_path: Path, metrics_path: Path, report: str) -> dict[str, Any]:
    checks = [
        report_path.as_posix().endswith("-opencode-usage.md"),
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
    report_path = _summary_dir(base_dir, d) / f"{d}-opencode-usage.md"
    report = render_report(metrics)
    metrics["policy_compliance"] = _write_policy(report_path, report_path, report)
    report = render_report(metrics)
    export_path = report_path.relative_to(base_dir / "data").as_posix()
    oc = metrics.get("opencode", {})
    submit_page_and_metrics(
        report=report,
        export_path=export_path,
        slug=report_path.stem,
        report_date=d,
        report_type="opencode",
        metrics=metrics,
        session_count=_int_or_none(oc.get("sessions", {}).get("total")),
        token_total=_int_or_none(oc.get("tokens", {}).get("total")),
        cost_usd=_float_or_none(oc.get("cost", {}).get("recorded_usd")),
        tool_error_count=_int_or_none(oc.get("error_rate", {}).get("tool_errors")),
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
    parser.add_argument("--opencode-db", type=Path, default=DEFAULT_OPENCODE_DB)
    parser.add_argument("--base-dir", type=Path, default=BASEDIR)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--lint", action="store_true")
    args = parser.parse_args(argv)

    metrics = collect_metrics(args.date, args.opencode_db)
    if args.dry_run:
        print(render_report(metrics))
        return 0
    outputs = write_outputs(metrics, args.base_dir)
    print("generated:")
    for key, path in outputs.items():
        print(f"- {key}: {path}")
    if args.lint:
        print("lint: skipped; service layer validates and exports Markdown on write")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
