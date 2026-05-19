#!/usr/bin/env python3
"""Deterministic Claude Code daily usage report generator."""

from __future__ import annotations

import argparse
import json
import subprocess
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from kb_mcp import REPO_ROOT as BASEDIR
from kb_mcp.cli.usage_reports.render import _fmt, _int, _num, _pct

DEFAULT_PROM = "http://127.0.0.1:9090"
DEFAULT_LOKI = "http://127.0.0.1:3110"
KST = timezone(timedelta(hours=9))
DEFERRED_METRICS = ["Task Completion Rate", "pass@k", "pass^k"]


def _kst_day_bounds(date_str: str) -> tuple[float, float]:
    d = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=KST)
    return d.timestamp(), (d + timedelta(days=1)).timestamp()


def _query_prom(base: str, expr: str, ts: float) -> list[dict[str, Any]]:
    params = urllib.parse.urlencode({"query": expr, "time": f"{ts:.3f}"})
    req = urllib.request.Request(f"{base}/api/v1/query?{params}")
    with urllib.request.urlopen(req, timeout=15) as resp:
        body = json.load(resp)
    return (
        body.get("data", {}).get("result", [])
        if body.get("status") == "success"
        else []
    )


def _query_loki(
    base: str,
    expr: str,
    start_ns: int,
    end_ns: int,
    limit: int = 5000,
    step: str | None = None,
) -> list[dict[str, Any]]:
    payload: dict[str, str] = {
        "query": expr,
        "start": str(start_ns),
        "end": str(end_ns),
        "limit": str(limit),
        "direction": "forward",
    }
    if step:
        payload["step"] = step
    params = urllib.parse.urlencode(payload)
    req = urllib.request.Request(f"{base}/loki/api/v1/query_range?{params}")
    with urllib.request.urlopen(req, timeout=60) as resp:
        body = json.load(resp)
    return (
        body.get("data", {}).get("result", [])
        if body.get("status") == "success"
        else []
    )


def _vec_sum(
    vec: list[dict[str, Any]],
    key_fn: Callable[[dict[str, str]], Any] = lambda m: "_all",
) -> dict[Any, float]:
    out: dict[Any, float] = defaultdict(float)
    for r in vec:
        out[key_fn(r["metric"])] += float(r["value"][1])
    return dict(out)


def _collect_prometheus(target_date: str, prom: str) -> dict[str, Any]:
    start_ts, end_ts = _kst_day_bounds(target_date)

    def inc(metric: str, grouping: str | None = None) -> str:
        body = f"increase({metric}[24h] @ {end_ts:.0f})"
        if grouping:
            body = f"sum by ({grouping}) ({body})"
        return body

    token_vec = _query_prom(
        prom,
        inc("claude_code_token_usage_tokens_total", "user_email,model,type"),
        end_ts,
    )
    cost_vec = _query_prom(
        prom, inc("claude_code_cost_usage_USD_total", "user_email,model"), end_ts
    )
    # session_count is emitted once per session-start, so increase() yields 0.
    # Counting unique series under the day window via a 24h-bracketed selector is more reliable.
    session_series = _query_prom(
        prom,
        f"count(count by (session_id) (last_over_time(claude_code_session_count_total[24h] @ {end_ts:.0f})))",
        end_ts,
    )
    sessions = float(session_series[0]["value"][1]) if session_series else 0.0
    active = _vec_sum(
        _query_prom(prom, inc("claude_code_active_time_seconds_total", "type"), end_ts),
        lambda m: m.get("type", "?"),
    )
    lines = _vec_sum(
        _query_prom(prom, inc("claude_code_lines_of_code_count_total", "type"), end_ts),
        lambda m: m.get("type", "?"),
    )
    decisions = _vec_sum(
        _query_prom(
            prom, inc("claude_code_code_edit_tool_decision_total", "decision"), end_ts
        ),
        lambda m: m.get("decision", "?"),
    )
    qsrc = _vec_sum(
        _query_prom(
            prom, inc("claude_code_token_usage_tokens_total", "query_source"), end_ts
        ),
        lambda m: m.get("query_source", "?"),
    )

    # Pivot tokens to (user_email, model) -> {type: count}
    tokens_by_pair: dict[tuple[str, str], dict[str, float]] = defaultdict(
        lambda: defaultdict(float)
    )
    for r in token_vec:
        m = r["metric"]
        pair = (m.get("user_email", "?"), m.get("model", "?"))
        tokens_by_pair[pair][m.get("type", "?")] += float(r["value"][1])

    cost_by_pair: dict[tuple[str, str], float] = defaultdict(float)
    for r in cost_vec:
        m = r["metric"]
        cost_by_pair[(m.get("user_email", "?"), m.get("model", "?"))] += float(
            r["value"][1]
        )

    model_usage = []
    totals = defaultdict(float)
    for pair, type_map in sorted(
        tokens_by_pair.items(), key=lambda kv: -sum(kv[1].values())
    ):
        user_email, model = pair
        input_t = type_map.get("input", 0.0)
        output = type_map.get("output", 0.0)
        cache_read = type_map.get("cacheRead", 0.0)
        cache_write = type_map.get("cacheCreation", 0.0)
        total_input = input_t + cache_read
        total = input_t + output + cache_read + cache_write
        cost = cost_by_pair.get(pair, 0.0)
        model_usage.append(
            {
                "user_email": user_email,
                "model": model,
                "input": int(total_input),
                "cache_miss": int(input_t),
                "cache_read": int(cache_read),
                "output": int(output),
                "cache_write": int(cache_write),
                "total": int(total),
                "cost": round(cost, 6),
                "cache_hit_pct": _pct_or_none(cache_read, total_input),
            }
        )
        totals["input"] += input_t
        totals["output"] += output
        totals["cache_read"] += cache_read
        totals["cache_write"] += cache_write
        totals["cost"] += cost
        totals["total"] += total

    total_input_all = totals["input"] + totals["cache_read"]
    cache_hit_pct = _pct_or_none(totals["cache_read"], total_input_all)

    return {
        "available": bool(token_vec or cost_vec),
        "sessions": {"total": int(sessions)},
        "tokens": {
            "input": int(totals["input"] + totals["cache_read"]),
            "cache_miss": int(totals["input"]),
            "cache_read": int(totals["cache_read"]),
            "output": int(totals["output"]),
            "cache_write": int(totals["cache_write"]),
            "total": int(totals["total"]),
            "cache_hit_pct": cache_hit_pct,
        },
        "cost": {
            "recorded_usd": round(totals["cost"], 6),
            "cost_per_session_usd": (
                round(totals["cost"] / sessions, 6) if sessions else None
            ),
        },
        "model_usage": model_usage,
        "active_time_seconds": {k: round(v, 2) for k, v in active.items()},
        "lines_of_code": {k: int(v) for k, v in lines.items()},
        "code_edit_decisions": {k: int(v) for k, v in decisions.items()},
        "query_source": {k: int(v) for k, v in qsrc.items()},
    }


def _pct_or_none(numerator: float, denominator: float) -> float | None:
    if denominator <= 0:
        return None
    return round(numerator * 100 / denominator, 2)


def _collect_loki(target_date: str, loki: str) -> dict[str, Any]:
    start_ts, end_ts = _kst_day_bounds(target_date)
    start_ns, end_ns = int(start_ts * 1e9), int(end_ts * 1e9)

    # event_name / tool_name / success are structured metadata (not stream labels),
    # so they need pipe filters and structured-metadata-aware grouping.
    tool_streams = _query_loki(
        loki,
        'sum by (tool_name, success) (count_over_time({service_name="claude-code"} | event_name="tool_result" [24h]))',
        start_ns,
        end_ns,
        limit=5000,
    )
    tool_breakdown: dict[str, dict[str, int]] = defaultdict(
        lambda: {"calls": 0, "errors": 0}
    )
    for stream in tool_streams:
        labels = stream.get("metric") or stream.get("stream") or {}
        tool = labels.get("tool_name", "unknown")
        success = labels.get("success", "true")
        count = sum(int(float(v[1])) for v in stream.get("values", []))
        tool_breakdown[tool]["calls"] += count
        if success != "true":
            tool_breakdown[tool]["errors"] += count
    tool_rows = sorted(
        (
            {"tool": t, **v, "error_rate_pct": _pct_or_none(v["errors"], v["calls"])}
            for t, v in tool_breakdown.items()
        ),
        key=lambda r: (-r["calls"], r["tool"]),
    )
    total_calls = sum(v["calls"] for v in tool_breakdown.values())
    total_errors = sum(v["errors"] for v in tool_breakdown.values())

    hourly_streams = _query_loki(
        loki,
        'sum by (session_id) (count_over_time({service_name="claude-code"}[1h]))',
        start_ns,
        end_ns,
        limit=5000,
        step="1h",
    )
    hourly: dict[str, set[str]] = defaultdict(set)
    sessions_seen: set[str] = set()
    for stream in hourly_streams:
        labels = stream.get("metric") or stream.get("stream") or {}
        sid = labels.get("session_id", "?")
        sessions_seen.add(sid)
        for ts, val in stream.get("values", []):
            # Loki matrix response: timestamp is float seconds, value is a string count.
            if float(val) <= 0:
                continue
            hour_kst = datetime.fromtimestamp(float(ts), tz=KST).strftime("%H")
            hourly[hour_kst].add(sid)
    hourly_rows = [
        {"hour": h, "sessions": len(sids)} for h, sids in sorted(hourly.items())
    ]

    duration_streams = _query_loki(
        loki,
        'avg by (tool_name) (avg_over_time({service_name="claude-code"} | event_name="tool_result" | unwrap duration_ms [24h]))',
        start_ns,
        end_ns,
        limit=2000,
    )
    latency_by_tool = []
    for stream in duration_streams:
        labels = stream.get("metric") or stream.get("stream") or {}
        vals = [
            float(v[1])
            for v in stream.get("values", [])
            if v[1] not in ("NaN", "+Inf", "-Inf")
        ]
        if not vals:
            continue
        latency_by_tool.append(
            {
                "tool": labels.get("tool_name", "?"),
                "avg_ms": round(sum(vals) / len(vals), 2),
                "max_ms": round(max(vals), 2),
            }
        )
    latency_by_tool.sort(key=lambda r: -r["avg_ms"])

    # Count distinct sessions per terminal_type, not raw entry counts.
    terminal_streams = _query_loki(
        loki,
        'sum by (terminal_type, session_id) (count_over_time({service_name="claude-code"}[24h]))',
        start_ns,
        end_ns,
        limit=5000,
    )
    terminal_sessions: dict[str, set[str]] = defaultdict(set)
    for s in terminal_streams:
        labels = s.get("metric") or s.get("stream") or {}
        terminal_sessions[labels.get("terminal_type", "?")].add(
            labels.get("session_id", "?")
        )
    terminal = {k: len(v) for k, v in terminal_sessions.items()}

    prompts = _query_loki(
        loki,
        'sum by (session_id) (count_over_time({service_name="claude-code"} | event_name="user_prompt" [24h]))',
        start_ns,
        end_ns,
        limit=5000,
    )
    n_turns = 0
    for s in prompts:
        n_turns += sum(int(float(v[1])) for v in s.get("values", []))

    return {
        "available": bool(tool_streams or hourly_streams),
        "sessions": {"loki_distinct": len(sessions_seen)},
        "n_turns": n_turns,
        "n_toolcalls": total_calls,
        "error_rate": {
            "tool_calls": total_calls,
            "tool_errors": total_errors,
            "rate_pct": _pct_or_none(total_errors, total_calls),
        },
        "tool_breakdown": tool_rows,
        "tool_latency": latency_by_tool[:10],
        "hourly_sessions": hourly_rows,
        "terminal_distribution": terminal,
    }


def collect_claude_code_metrics(
    target_date: str, prom: str = DEFAULT_PROM, loki: str = DEFAULT_LOKI
) -> dict[str, Any]:
    p = _collect_prometheus(target_date, prom)
    lk = _collect_loki(target_date, loki)
    return {
        "date": target_date,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "deferred_metrics": DEFERRED_METRICS,
        "claude_code": {
            **p,
            **{k: v for k, v in lk.items() if k != "sessions"},
            "sessions": {**p.get("sessions", {}), **lk.get("sessions", {})},
        },
        "policy_compliance": {
            "passed": 0,
            "total": 0,
            "rate_pct": None,
            "status": "not_evaluated_until_write",
        },
    }


def _model_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "- Model usage: N/A"
    out = [
        "| user | model | total | total_input | cache_miss | cache_read | output | cache_write | cache_hit | cost USD |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in rows:
        out.append(
            f"| {r.get('user_email')} | {r.get('model')} | {_int(r.get('total'))} | {_int(r.get('input'))} | "
            f"{_int(r.get('cache_miss'))} | {_int(r.get('cache_read'))} | {_int(r.get('output'))} | "
            f"{_int(r.get('cache_write'))} | {_pct(r.get('cache_hit_pct'))} | {_fmt(r.get('cost'))} |"
        )
    return "\n".join(out)


def _tool_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "- Tool usage: N/A"
    out = ["| tool | calls | errors | error_rate |", "|---|---:|---:|---:|"]
    for r in rows:
        out.append(
            f"| {r.get('tool')} | {_int(r.get('calls'))} | {_int(r.get('errors'))} | {_pct(r.get('error_rate_pct'))} |"
        )
    return "\n".join(out)


def _latency_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "- Average tool duration: N/A"
    out = ["| tool | avg_ms | max_ms |", "|---|---:|---:|"]
    for r in rows:
        out.append(
            f"| {r.get('tool')} | {_fmt(r.get('avg_ms'))} | {_fmt(r.get('max_ms'))} |"
        )
    return "\n".join(out)


def _hourly_lines(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "- Hourly distribution: N/A"
    return "\n".join(
        f"  - {r.get('hour')}: {_fmt(r.get('sessions'))} sessions" for r in rows
    )


def _dict_lines(d: dict[str, Any], suffix: str = "") -> str:
    if not d:
        return "  - N/A"
    return "\n".join(
        f"  - {k}: {_fmt(v)}{suffix}"
        for k, v in sorted(d.items(), key=lambda kv: -_num(kv[1]))
    )


def _observations(metrics: dict[str, Any]) -> list[str]:
    cc = metrics["claude_code"]
    obs: list[str] = []
    tokens = cc.get("tokens", {})
    hit = tokens.get("cache_hit_pct")
    if hit is not None and hit >= 90:
        obs.append(
            f"Cache hit rate is {_pct(hit)}; repeated-context work is likely reducing cost. Monitor cache_read share changes."
        )
    elif hit is not None and hit < 50 and tokens.get("total", 0) > 0:
        obs.append(
            f"Cache hit rate is low at {_pct(hit)}; many new sessions or frequent context invalidation may be reducing cost efficiency."
        )
    err = cc.get("error_rate", {})
    if err.get("rate_pct") is not None and err.get("rate_pct") > 5:
        obs.append(
            f"Overall tool error rate is {_pct(err.get('rate_pct'))}; review precheck and tool-call patterns."
        )
    decisions = cc.get("code_edit_decisions", {})
    accept = _num(decisions.get("accept"))
    reject = _num(decisions.get("reject"))
    if accept + reject > 0:
        accept_rate = _pct_or_none(accept, accept + reject)
        obs.append(
            f"Code edit accept rate is {_pct(accept_rate)} ({int(accept)}/{int(accept + reject)}); low rates may signal prompt or tool-result quality issues."
        )
    hourly = cc.get("hourly_sessions", [])
    if hourly:
        peak = max(hourly, key=lambda r: _num(r.get("sessions")))
        obs.append(
            f"Usage peak at hour {peak.get('hour')} with {_fmt(peak.get('sessions'))} sessions; useful for automation and focus-pattern tracking."
        )
    qsrc = cc.get("query_source", {})
    aux = _num(qsrc.get("auxiliary"))
    main = _num(qsrc.get("main"))
    if main + aux > 0:
        aux_pct = _pct_or_none(aux, main + aux)
        obs.append(
            f"Auxiliary query share is {_pct(aux_pct)}; this is a rough proxy for sub-agent/background workload."
        )
    if not obs:
        obs.append("No notable signals. Current values can be used as baseline.")
    return obs


def render_daily_report(metrics: dict[str, Any]) -> str:
    d = metrics["date"]
    cc = metrics["claude_code"]
    pc = metrics["policy_compliance"]
    sessions = cc.get("sessions", {})
    sessions.get("total") or sessions.get("loki_distinct") or 0
    tokens = cc.get("tokens", {})
    cost = cc.get("cost", {})
    err = cc.get("error_rate", {})
    decisions = cc.get("code_edit_decisions", {})
    lines = cc.get("lines_of_code", {})
    active = cc.get("active_time_seconds", {})
    active_total = sum(_num(v) for v in active.values())
    observations = "\n".join(f"- {line}" for line in _observations(metrics))

    return f"""---
type: summary
subtype: daily
date: \"{d}\"
created: \"{d}\"
updated: \"{d}\"
sources: []
tags: [agent-usage, deterministic-report, claude-code]
---

# Claude Code Daily Report — {d}

## Summary

- Sessions: counter {_fmt(sessions.get('total'))} / Loki distinct {_fmt(sessions.get('loki_distinct'))}
- Turns (user_prompt): {_int(cc.get('n_turns'))}
- Tool calls: {_int(cc.get('n_toolcalls'))} (errors {_int(err.get('tool_errors'))}, rate {_pct(err.get('rate_pct'))})
- Total tokens: {_int(tokens.get('total'))} (input {_int(tokens.get('input'))} / output {_int(tokens.get('output'))} / cache_read {_int(tokens.get('cache_read'))} / cache_write {_int(tokens.get('cache_write'))})
- Recorded cost: {_fmt(cost.get('recorded_usd'))} USD
- Cache hit rate: {_pct(tokens.get('cache_hit_pct'))}
- Code edit decisions: accept {_int(decisions.get('accept'))} / reject {_int(decisions.get('reject'))}
- Lines of code: added {_int(lines.get('added'))} / removed {_int(lines.get('removed'))}
- Active time: {_fmt(round(active_total, 1))}s ({_fmt(round(active_total / 60, 1))}m)

## Development/Evaluation Metrics

| Metric | Claude Code | Status |
|---|---:|---|
| Task Completion Rate | code_edit accept rate {_pct(_pct_or_none(_num(decisions.get('accept')), _num(decisions.get('accept')) + _num(decisions.get('reject'))))} proxy | true task schema needed |
| pass@k / pass^k | deferred | eval-run schema needed |
| Error Rate | {_int(err.get('tool_errors'))}/{_int(err.get('tool_calls'))} ({_pct(err.get('rate_pct'))}) | deterministic |
| Hallucinated Parameters | N/A | Claude Code tools are validated client-side |
| n_toolcalls / n_turns | {_int(cc.get('n_toolcalls'))} / {_int(cc.get('n_turns'))} | deterministic |
| Total Token Usage / Cost | {_int(tokens.get('total'))} tok / {_fmt(cost.get('recorded_usd'))} USD ({_fmt(cost.get('cost_per_session_usd'))} USD/session) | deterministic |
| Policy Compliance Rate | {_pct(pc.get('rate_pct'))} | {pc.get('status')} |

## Layer 1: Cost and Efficiency

- Total tokens: {_int(tokens.get('total'))} (input {_int(tokens.get('input'))} / output {_int(tokens.get('output'))} / cache_read {_int(tokens.get('cache_read'))} / cache_write {_int(tokens.get('cache_write'))})
- Cache hit rate: {_pct(tokens.get('cache_hit_pct'))} (cache_read / (cache_miss + cache_read))
- Recorded cost: {_fmt(cost.get('recorded_usd'))} USD ({_fmt(cost.get('cost_per_session_usd'))} USD/session)
- User/model usage:

{_model_table(cc.get('model_usage', []))}

## Layer 2: Work Quality

- Tool calls: {_int(cc.get('n_toolcalls'))}, errors: {_int(err.get('tool_errors'))} ({_pct(err.get('rate_pct'))})
- Tool usage:

{_tool_table(cc.get('tool_breakdown', []))}

- Code edit decisions: accept {_int(decisions.get('accept'))} / reject {_int(decisions.get('reject'))}
- Lines of code: added {_int(lines.get('added'))} / removed {_int(lines.get('removed'))}

## Layer 3: Behavior Pattern

- Hourly distribution (unique sessions):
{_hourly_lines(cc.get('hourly_sessions', []))}
- Query source distribution (token-weighted):
{_dict_lines(cc.get('query_source', {}), suffix=' tokens')}
- Average tool duration top 10:

{_latency_table(cc.get('tool_latency', []))}

## Layer 4: Focus and Stability

- Terminal type distribution (log entry count):
{_dict_lines(cc.get('terminal_distribution', {}))}
- Active time by type (seconds):
{_dict_lines(active)}
- Counter sessions: {_fmt(sessions.get('total'))}, Loki distinct sessions: {_fmt(sessions.get('loki_distinct'))}

## Problems / Improvement Candidates

{observations}
"""


def _write_policy(report_path: Path, metrics_path: Path, report: str) -> dict[str, Any]:
    checks = [
        report_path.as_posix().endswith("-claude-code-usage.md"),
        "/data/wiki/summaries/" in report_path.as_posix(),
        "/data/ops/reports/" in metrics_path.as_posix(),
        "sources: []" in report,
        "$" not in report,
    ]
    passed = sum(1 for c in checks if c)
    return {
        "passed": passed,
        "total": len(checks),
        "rate_pct": _pct_or_none(passed, len(checks)),
        "status": "evaluated",
    }


def write_outputs(metrics: dict[str, Any], base_dir: Path = BASEDIR) -> dict[str, Path]:
    d = metrics["date"]
    year, month, _ = d.split("-")
    report_path = (
        base_dir / "data/wiki/summaries" / year / month / f"{d}-claude-code-usage.md"
    )
    metrics_path = (
        base_dir
        / "data/ops/reports"
        / year
        / month
        / f"{d}-claude-code-usage.metrics.json"
    )
    report = render_daily_report(metrics)
    metrics["policy_compliance"] = _write_policy(report_path, metrics_path, report)
    report = render_daily_report(metrics)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")
    metrics_path.write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {"report": report_path, "metrics": metrics_path}


def _default_target_date() -> str:
    return (datetime.now(KST).date() - timedelta(days=1)).isoformat()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", default=_default_target_date())
    parser.add_argument("--prom", default=DEFAULT_PROM)
    parser.add_argument("--loki", default=DEFAULT_LOKI)
    parser.add_argument("--base-dir", type=Path, default=BASEDIR)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--lint", action="store_true")
    args = parser.parse_args(argv)

    metrics = collect_claude_code_metrics(args.date, args.prom, args.loki)
    if args.dry_run:
        print(render_daily_report(metrics))
        return 0
    outputs = write_outputs(metrics, args.base_dir)
    print("generated:")
    for key, path in outputs.items():
        print(f"- {key}: {path}")
    if args.lint:
        index_result = subprocess.run(
            ["uv", "run", "kb-wiki-index"], cwd=args.base_dir, text=True
        )
        if index_result.returncode != 0:
            return index_result.returncode
        result = subprocess.run(
            ["uv", "run", "kb-lint-wiki"], cwd=args.base_dir, text=True
        )
        return result.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
