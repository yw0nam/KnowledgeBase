"""Shared markdown helpers for deterministic usage reports."""

from __future__ import annotations

from pathlib import PurePath
from typing import Any


def _num(value: Any) -> float:
    return float(value or 0)


def _fmt(value: Any) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, float):
        return f"{value:.2f}" if not value.is_integer() else str(int(value))
    return str(value)


def _int(value: Any) -> str:
    return f"{int(_num(value)):,}"


def _pct(value: Any) -> str:
    return "N/A" if value is None else f"{_fmt(value)}%"


def _schema_cell(system: dict[str, Any]) -> str:
    s = system.get("tool_schema", {})
    examples = s.get("examples") or []
    suffix = f"; example: {examples[0]}" if examples else ""
    return f"{_fmt(s.get('invalid_calls'))}/{_fmt(s.get('validated_calls'))} invalid, compliance {_fmt(s.get('compliance_rate_pct'))}%{suffix}"


def _model_table(rows: list[dict[str, Any]], include_sessions: bool = False) -> str:
    if not rows:
        return "- Model usage: N/A"
    session_col = " | sessions" if include_sessions else ""
    out = [
        f"| model | provider{session_col} | total | total_input | cache_miss | cache_read | output | cache_write | reasoning | cache_hit | cost USD |",
        f"|---|---:{'|---:' if include_sessions else ''}|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in rows:
        model = r.get("model") or "unknown"
        provider = r.get("provider") or "unknown"
        sessions = f" | {_int(r.get('sessions'))}" if include_sessions else ""
        out.append(
            f"| {model} | {provider}{sessions} | {_int(r.get('total'))} | {_int(r.get('input'))} | {_int(r.get('cache_miss'))} | {_int(r.get('cache_read'))} | {_int(r.get('output'))} | {_int(r.get('cache_write'))} | {_int(r.get('reasoning'))} | {_pct(r.get('cache_hit_pct'))} | {_fmt(r.get('cost'))} |"
        )
    return "\n".join(out)


def _tool_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "- Tool errors: N/A"
    out = ["| tool | calls | errors | error_rate |", "|---|---:|---:|---:|"]
    for r in rows:
        out.append(f"| {r.get('tool')} | {_int(r.get('calls'))} | {_int(r.get('errors'))} | {_pct(r.get('error_rate_pct'))} |")
    return "\n".join(out)


def _hourly_lines(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "- Hourly distribution: N/A"
    lines = []
    for r in rows:
        extra = ""
        if "root" in r:
            extra = f" (root {_fmt(r.get('root'))} / subagent {_fmt(r.get('subagent'))})"
        lines.append(f"  - {r.get('hour')}: {_fmt(r.get('sessions'))} sessions{extra}")
    return "\n".join(lines)


def _kv_lines(rows: list[dict[str, Any]], key: str, value: str = "sessions", limit: int = 8) -> str:
    if not rows:
        return "  - N/A"
    return "\n".join(f"  - {r.get(key)}: {_fmt(r.get(value))}" for r in rows[:limit])


def _hot_files(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "  - N/A"
    lines = []
    for r in rows[:8]:
        name = PurePath(str(r.get("file"))).name
        lines.append(f"  - {name}: {_fmt(r.get('edits'))} edits ({r.get('file')})")
    return "\n".join(lines)
