"""Markdown renderer for deterministic daily usage reports."""

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
    suffix = f"; 예: {examples[0]}" if examples else ""
    return f"{_fmt(s.get('invalid_calls'))}/{_fmt(s.get('validated_calls'))} invalid, compliance {_fmt(s.get('compliance_rate_pct'))}%{suffix}"


def _model_table(rows: list[dict[str, Any]], include_sessions: bool = False) -> str:
    if not rows:
        return "- 모델별 사용량: N/A"
    session_col = " | sessions" if include_sessions else ""
    out = [
        f"| 모델 | provider{session_col} | total | total_input | cache_miss | cache_read | output | cache_write | reasoning | cache_hit | cost USD |",
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
        return "- 도구별 에러: N/A"
    out = ["| tool | calls | errors | error_rate |", "|---|---:|---:|---:|"]
    for r in rows:
        out.append(f"| {r.get('tool')} | {_int(r.get('calls'))} | {_int(r.get('errors'))} | {_pct(r.get('error_rate_pct'))} |")
    return "\n".join(out)


def _hourly_lines(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "- 시간대 분포: N/A"
    lines = []
    for r in rows:
        extra = ""
        if "root" in r:
            extra = f" (root {_fmt(r.get('root'))} / subagent {_fmt(r.get('subagent'))})"
        lines.append(f"  - {r.get('hour')}시: {_fmt(r.get('sessions'))}세션{extra}")
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
        lines.append(f"  - {name}: {_fmt(r.get('edits'))}회 ({r.get('file')})")
    return "\n".join(lines)


def _observations(metrics: dict[str, Any]) -> list[str]:
    oc = metrics["opencode"]
    he = metrics["hermes"]
    obs: list[str] = []
    cache_models = [r for r in oc.get("model_usage", []) if _num(r.get("cache_hit_pct")) >= 95]
    if cache_models:
        names = ", ".join(str(r.get("model")) for r in cache_models[:3])
        obs.append(f"OpenCode 캐시 히트율이 높은 모델({names})이 있음. 반복 컨텍스트 기반 집중 작업 패턴으로 보이며, 비용은 cache_read 비중에 민감함.")
    todo = oc.get("todo", {})
    if todo.get("total"):
        obs.append(f"OpenCode TODO 완료율은 {_pct(todo.get('completion_rate_pct'))} ({_fmt(todo.get('completed'))}/{_fmt(todo.get('total'))}). 완료율이 낮아지면 task schema 기반 Completion Rate로 승격 가능함.")
    errors = [r for r in oc.get("tool_breakdown", []) if _num(r.get("errors")) > 0]
    if errors:
        worst = sorted(errors, key=lambda r: (_num(r.get("error_rate_pct")), _num(r.get("errors"))), reverse=True)[0]
        obs.append(f"도구 에러는 {worst.get('tool')}에서 가장 눈에 띔: {_fmt(worst.get('errors'))}/{_fmt(worst.get('calls'))} ({_pct(worst.get('error_rate_pct'))}). 반복되면 해당 도구 호출 전 precheck가 필요함.")
    hourly = oc.get("hourly_sessions", [])
    if hourly:
        peak = max(hourly, key=lambda r: _num(r.get("sessions")))
        obs.append(f"OpenCode 사용 피크는 {peak.get('hour')}시 {_fmt(peak.get('sessions'))}세션. 시간대별 집중/자동화 패턴 추적에 유효함.")
    projects = oc.get("projects", [])
    if projects:
        top = projects[0]
        obs.append(f"주요 작업 프로젝트는 {top.get('project')} ({_fmt(top.get('sessions'))}세션). 프로젝트 쏠림과 전환 비용을 계속 추적해야 함.")
    if _num(he.get("sessions", {}).get("zombie")) > 0:
        obs.append(f"Hermes zombie 세션 {_fmt(he.get('sessions', {}).get('zombie'))}건 발견. TUI/cron 종료 처리를 점검해야 함.")
    if not obs:
        obs.append("특이 신호 없음. 현재 수치는 baseline으로 사용 가능함.")
    return obs


def render_daily_report(metrics: dict[str, Any]) -> str:
    d = metrics["date"]
    oc = metrics["opencode"]
    he = metrics["hermes"]
    pc = metrics["policy_compliance"]
    total_cost = _num(oc.get("cost", {}).get("recorded_usd")) + _num(he.get("cost", {}).get("recorded_usd"))
    total_tokens = int(_num(oc.get("tokens", {}).get("total")) + _num(he.get("tokens", {}).get("total")))
    todo = oc.get("todo", {})
    delegation_rate = None
    if _num(oc.get("sessions", {}).get("total")):
        delegation_rate = round(_num(oc.get("sessions", {}).get("subagent")) * 100 / _num(oc.get("sessions", {}).get("total")), 2)
    observations = "\n".join(f"- {line}" for line in _observations(metrics))
    return f"""---
type: summary
subtype: daily
date: \"{d}\"
created: \"{d}\"
updated: \"{d}\"
sources: []
tags: [agent-usage, deterministic-report]
---

# Daily Report — {d}

## Summary

- OpenCode: 총 {_fmt(oc.get('sessions', {}).get('total'))}세션 (root {_fmt(oc.get('sessions', {}).get('root'))} / subagent {_fmt(oc.get('sessions', {}).get('subagent'))}), 프로젝트 {_fmt(oc.get('sessions', {}).get('projects'))}개
- Hermes: root {_fmt(he.get('sessions', {}).get('root'))}세션, zombie {_fmt(he.get('sessions', {}).get('zombie'))}건
- 총 토큰: {total_tokens:,}
- 총 기록 비용: {total_cost:.6f} USD
- OpenCode TODO 완료율: {_pct(todo.get('completion_rate_pct'))} ({_fmt(todo.get('completed'))}/{_fmt(todo.get('total'))})
- OpenCode 위임율: {_pct(delegation_rate)}

## Development/Evaluation Metrics

| Metric | OpenCode | Hermes | Status |
|---|---:|---:|---|
| Task Completion Rate | TODO proxy {_pct(todo.get('completion_rate_pct'))} ({_fmt(todo.get('completed'))}/{_fmt(todo.get('total'))}) | N/A | task schema needed for true eval |
| pass@k / pass^k | 보류 | 보류 | eval-run schema needed |
| Error Rate | {_fmt(oc.get('error_rate', {}).get('tool_errors'))}/{_fmt(oc.get('error_rate', {}).get('tool_calls'))} ({_fmt(oc.get('error_rate', {}).get('rate_pct'))}%) | N/A | deterministic where available |
| Hallucinated Parameters | {_schema_cell(oc)} | {_schema_cell(he)} | deterministic schema check |
| n_toolcalls / n_turns | {_fmt(oc.get('n_toolcalls'))} / {_fmt(oc.get('n_turns'))} | {_fmt(he.get('n_toolcalls'))} / {_fmt(he.get('n_turns'))} | deterministic |
| Total Token Usage / Latency / Number of Turns / Cost per Task | {oc.get('tokens', {}).get('total', 0):,} tok / avg {_fmt(oc.get('latency', {}).get('avg_session_sec'))}s / {_fmt(oc.get('n_turns'))} turns / {_fmt(oc.get('cost', {}).get('cost_per_session_usd'))} USD/session | {he.get('tokens', {}).get('total', 0):,} tok / avg {_fmt(he.get('latency', {}).get('avg_session_sec'))}s / {_fmt(he.get('n_turns'))} turns / {_fmt(he.get('cost', {}).get('cost_per_session_usd'))} USD/session | deterministic |
| Policy Compliance Rate | {_pct(pc.get('rate_pct'))} | {_pct(pc.get('rate_pct'))} | {pc.get('status')} |

## Layer 1: 비용·효율

**OpenCode**

- 총 토큰: {oc.get('tokens', {}).get('total', 0):,} (input {oc.get('tokens', {}).get('input', 0):,} / output {oc.get('tokens', {}).get('output', 0):,} / cache_read {oc.get('tokens', {}).get('cache_read', 0):,} / cache_write {oc.get('tokens', {}).get('cache_write', 0):,} / reasoning {oc.get('tokens', {}).get('reasoning', 0):,})
- 기록 비용: {_fmt(oc.get('cost', {}).get('recorded_usd'))} USD
- 평균 세션 시간: {_fmt(oc.get('latency', {}).get('avg_session_sec'))}초 / 최대 {_fmt(oc.get('latency', {}).get('max_session_sec'))}초
- 모델별 사용량:

{_model_table(oc.get('model_usage', []))}

**Hermes**

- 총 토큰: {he.get('tokens', {}).get('total', 0):,} (input {he.get('tokens', {}).get('input', 0):,} / output {he.get('tokens', {}).get('output', 0):,} / cache_read {he.get('tokens', {}).get('cache_read', 0):,} / cache_write {he.get('tokens', {}).get('cache_write', 0):,} / reasoning {he.get('tokens', {}).get('reasoning', 0):,})
- 기록 비용: {_fmt(he.get('cost', {}).get('recorded_usd'))} USD
- 평균 세션 시간: {_fmt(he.get('latency', {}).get('avg_session_sec'))}초 / 최대 {_fmt(he.get('latency', {}).get('max_session_sec'))}초
- 모델별 사용량:

{_model_table(he.get('model_usage', []), include_sessions=True)}

## Layer 2: 작업 품질

**OpenCode**

- TODO 완료율: {_pct(todo.get('completion_rate_pct'))} ({_fmt(todo.get('completed'))}/{_fmt(todo.get('total'))}) — cancelled {_fmt(todo.get('cancelled'))}, pending {_fmt(todo.get('pending'))}, in_progress {_fmt(todo.get('in_progress'))}
- 전체 도구 에러율: {_fmt(oc.get('error_rate', {}).get('rate_pct'))}% ({_fmt(oc.get('error_rate', {}).get('tool_errors'))}/{_fmt(oc.get('error_rate', {}).get('tool_calls'))})
- 도구별 에러:

{_tool_table(oc.get('tool_breakdown', []))}

- Hallucinated Parameters: {_schema_cell(oc)}
- compaction: {_fmt(oc.get('sessions', {}).get('compactions'))}건

**Hermes**

- end_reason 분포:
{_kv_lines(he.get('end_reason_distribution', []), 'end_reason')}
- source 분포:
{_kv_lines(he.get('source_distribution', []), 'source')}
- 좀비 세션: {_fmt(he.get('sessions', {}).get('zombie'))}건
- Hallucinated Parameters: {_schema_cell(he)}

## Layer 3: 행동 패턴

**OpenCode**

- 시간대 분포 (KST):
{_hourly_lines(oc.get('hourly_sessions', []))}
- root vs subagent: root {_fmt(oc.get('sessions', {}).get('root'))} / subagent {_fmt(oc.get('sessions', {}).get('subagent'))} (위임율 {_pct(delegation_rate)})
- n_toolcalls / n_turns: {_fmt(oc.get('n_toolcalls'))} / {_fmt(oc.get('n_turns'))}

**Hermes**

- 시간대 분포 (KST):
{_hourly_lines(he.get('hourly_sessions', []))}
- root sessions: {_fmt(he.get('sessions', {}).get('root'))}
- n_toolcalls / n_turns: {_fmt(he.get('n_toolcalls'))} / {_fmt(he.get('n_turns'))}

## Layer 4: 집중도·안정성

**OpenCode**

- 프로젝트 분포:
{_kv_lines(oc.get('projects', []), 'project')}
- 핫 파일:
{_hot_files(oc.get('hot_files', []))}
- 세션 summary_files 합계: {_fmt(oc.get('sessions', {}).get('summary_files'))}
- schema-unvalidated tool calls: {_fmt(oc.get('tool_schema', {}).get('unvalidated_calls'))}

**Hermes**

- 모델별 세션:
{_kv_lines(he.get('model_usage', []), 'model')}
- max session latency: {_fmt(he.get('latency', {}).get('max_session_sec'))}초

## Problems / Improvement Candidates

{observations}
"""
