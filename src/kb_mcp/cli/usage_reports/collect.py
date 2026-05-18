#!/usr/bin/env python3
"""Shared collectors for deterministic usage reports."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

BASEDIR = Path(__file__).resolve().parent.parent.parent.parent
DEFAULT_OPENCODE_DB = Path.home() / ".local/share/opencode/opencode.db"
DEFAULT_HERMES_DB = Path.home() / ".hermes/state.db"
DEFERRED_METRICS = ["Task Completion Rate", "pass@k", "pass^k"]

TOOL_SCHEMAS: dict[str, dict[str, set[str]]] = {
    # Hermes tools
    "terminal": {"required": {"command"}, "allowed": {"command", "timeout", "workdir", "background", "pty", "notify_on_complete", "watch_patterns"}},
    "read_file": {"required": {"path"}, "allowed": {"path", "offset", "limit"}},
    "search_files": {"required": {"pattern"}, "allowed": {"pattern", "target", "path", "file_glob", "limit", "offset", "output_mode", "context"}},
    "write_file": {"required": {"path", "content"}, "allowed": {"path", "content"}},
    "patch": {"required": {"mode"}, "allowed": {"mode", "path", "old_string", "new_string", "replace_all", "patch"}},
    "skill_view": {"required": {"name"}, "allowed": {"name", "file_path"}},
    "skill_manage": {"required": {"action", "name"}, "allowed": {"action", "name", "content", "old_string", "new_string", "replace_all", "category", "file_path", "file_content", "absorbed_into"}},
    "todo": {"required": set(), "allowed": {"todos", "merge"}},
    "cronjob": {"required": {"action"}, "allowed": {"action", "job_id", "prompt", "schedule", "name", "repeat", "deliver", "skills", "model", "script", "no_agent", "context_from", "enabled_toolsets", "workdir"}},
    # OpenCode tools
    "bash": {"required": {"command"}, "allowed": {"command", "description", "timeout", "workdir"}},
    "read": {"required": {"filePath"}, "allowed": {"filePath", "offset", "limit"}},
    "write": {"required": {"filePath", "content"}, "allowed": {"filePath", "content"}},
    "edit": {"required": {"filePath", "oldString", "newString"}, "allowed": {"filePath", "oldString", "newString", "replaceAll"}},
    "todowrite": {"required": {"todos"}, "allowed": {"todos"}},
    "webfetch": {"required": {"url"}, "allowed": {"url", "format", "timeout"}},
}


def _connect(path: Path) -> sqlite3.Connection | None:
    if not path.exists():
        return None
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    return con


def _one(con: sqlite3.Connection, sql: str, args: tuple[Any, ...]) -> dict[str, Any]:
    row = con.execute(sql, args).fetchone()
    return dict(row) if row else {}


def _rows(con: sqlite3.Connection, sql: str, args: tuple[Any, ...]) -> list[dict[str, Any]]:
    return [dict(row) for row in con.execute(sql, args).fetchall()]


def _has_table(con: sqlite3.Connection, name: str) -> bool:
    row = con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone()
    return row is not None


def _num(value: Any) -> float:
    return float(value or 0)


def _pct(numerator: float, denominator: float) -> float | None:
    if denominator <= 0:
        return None
    return round(numerator * 100 / denominator, 2)


def _validate_tool_call(tool: str | None, args: Any) -> list[str]:
    if not tool or tool not in TOOL_SCHEMAS:
        return []
    if isinstance(args, str):
        try:
            args = json.loads(args) if args else {}
        except json.JSONDecodeError:
            return ["arguments_json_parse_error"]
    if not isinstance(args, dict):
        return ["arguments_not_object"]
    schema = TOOL_SCHEMAS[tool]
    errors: list[str] = []
    missing = schema["required"] - set(args)
    extra = set(args) - schema["allowed"]
    if missing:
        errors.append("missing:" + ",".join(sorted(missing)))
    if extra:
        errors.append("extra:" + ",".join(sorted(extra)))
    return errors


def _tool_schema_summary(calls: list[tuple[str | None, Any]]) -> dict[str, Any]:
    validated = invalid = unvalidated = 0
    examples: list[str] = []
    for tool, args in calls:
        if not tool or tool not in TOOL_SCHEMAS:
            unvalidated += 1
            continue
        validated += 1
        errors = _validate_tool_call(tool, args)
        if errors:
            invalid += 1
            if len(examples) < 5:
                examples.append(f"{tool}: {'; '.join(errors)}")
    return {
        "validated_calls": validated,
        "invalid_calls": invalid,
        "unvalidated_calls": unvalidated,
        "compliance_rate_pct": _pct(validated - invalid, validated),
        "examples": examples,
    }


def _collect_opencode(target_date: str, db_path: Path) -> dict[str, Any]:
    con = _connect(db_path)
    if con is None:
        return {"available": False, "reason": f"missing db: {db_path}"}
    sessions = _one(
        con,
        """
        SELECT count(*) total,
               coalesce(sum(parent_id IS NULL), 0) root,
               coalesce(sum(parent_id IS NOT NULL), 0) subagent,
               count(distinct project_id) projects,
               avg((time_updated - time_created) / 1000.0) avg_session_sec,
               max((time_updated - time_created) / 1000.0) max_session_sec,
               coalesce(sum(coalesce(summary_files, 0)), 0) summary_files,
               coalesce(sum(time_compacting IS NOT NULL), 0) compactions
        FROM session
        WHERE date(datetime(time_created/1000, 'unixepoch', '+9 hours')) = ?
        """,
        (target_date,),
    )
    tokens = _one(
        con,
        """
        SELECT coalesce(sum(json_extract(m.data, '$.tokens.input')), 0) input,
               coalesce(sum(json_extract(m.data, '$.tokens.output')), 0) output,
               coalesce(sum(json_extract(m.data, '$.tokens.reasoning')), 0) reasoning,
               coalesce(sum(json_extract(m.data, '$.tokens.cache.read')), 0) cache_read,
               coalesce(sum(json_extract(m.data, '$.tokens.cache.write')), 0) cache_write,
               coalesce(sum(json_extract(m.data, '$.cost')), 0) recorded_usd
        FROM message m
        JOIN session s ON m.session_id = s.id
        WHERE date(datetime(s.time_created/1000, 'unixepoch', '+9 hours')) = ?
          AND json_extract(m.data, '$.role') = 'assistant'
        """,
        (target_date,),
    )
    model_rows = _rows(
        con,
        """
        SELECT coalesce(json_extract(m.data, '$.modelID'), s.model, 'unknown') model,
               coalesce(json_extract(m.data, '$.providerID'), 'unknown') provider,
               coalesce(sum(json_extract(m.data, '$.tokens.input')), 0) input,
               coalesce(sum(json_extract(m.data, '$.tokens.output')), 0) output,
               coalesce(sum(json_extract(m.data, '$.tokens.reasoning')), 0) reasoning,
               coalesce(sum(json_extract(m.data, '$.tokens.cache.read')), 0) cache_read,
               coalesce(sum(json_extract(m.data, '$.tokens.cache.write')), 0) cache_write,
               coalesce(sum(json_extract(m.data, '$.cost')), 0) cost,
               count(*) messages
        FROM message m
        JOIN session s ON m.session_id = s.id
        WHERE date(datetime(s.time_created/1000, 'unixepoch', '+9 hours')) = ?
          AND json_extract(m.data, '$.role') = 'assistant'
        GROUP BY 1, 2
        ORDER BY (input + output + reasoning + cache_read + cache_write) DESC
        """,
        (target_date,),
    )
    turns = _one(
        con,
        """
        SELECT count(*) n_turns
        FROM message m
        JOIN session s ON m.session_id = s.id
        WHERE date(datetime(s.time_created/1000, 'unixepoch', '+9 hours')) = ?
        """,
        (target_date,),
    )
    tool = _one(
        con,
        """
        SELECT count(*) tool_calls,
               coalesce(sum(json_extract(data, '$.state.status') = 'error'), 0) tool_errors
        FROM part
        WHERE json_extract(data, '$.type') = 'tool'
          AND date(datetime(time_created/1000, 'unixepoch', '+9 hours')) = ?
        """,
        (target_date,),
    )
    tool_breakdown = _rows(
        con,
        """
        SELECT coalesce(json_extract(data, '$.tool'), 'unknown') tool,
               count(*) calls,
               coalesce(sum(json_extract(data, '$.state.status') = 'error'), 0) errors
        FROM part
        WHERE json_extract(data, '$.type') = 'tool'
          AND date(datetime(time_created/1000, 'unixepoch', '+9 hours')) = ?
        GROUP BY tool
        ORDER BY calls DESC, tool ASC
        """,
        (target_date,),
    )
    tool_rows = _rows(
        con,
        """
        SELECT json_extract(data, '$.tool') tool,
               json_extract(data, '$.state.input') input
        FROM part
        WHERE json_extract(data, '$.type') = 'tool'
          AND date(datetime(time_created/1000, 'unixepoch', '+9 hours')) = ?
        """,
        (target_date,),
    )
    hourly = _rows(
        con,
        """
        SELECT strftime('%H', datetime(time_created/1000, 'unixepoch', '+9 hours')) hour,
               count(*) sessions,
               coalesce(sum(parent_id IS NULL), 0) root,
               coalesce(sum(parent_id IS NOT NULL), 0) subagent
        FROM session
        WHERE date(datetime(time_created/1000, 'unixepoch', '+9 hours')) = ?
        GROUP BY hour
        ORDER BY hour
        """,
        (target_date,),
    )
    project_rows = _rows(
        con,
        """
        SELECT coalesce(p.name, replace(s.directory, rtrim(s.directory, replace(s.directory, '/', '')), ''), s.project_id) project,
               coalesce(p.worktree, s.directory) path,
               count(*) sessions
        FROM session s
        LEFT JOIN project p ON p.id = s.project_id
        WHERE date(datetime(s.time_created/1000, 'unixepoch', '+9 hours')) = ?
        GROUP BY s.project_id
        ORDER BY sessions DESC, project ASC
        """,
        (target_date,),
    )
    if _has_table(con, "todo"):
        todo_rows = _rows(
            con,
            """
            SELECT status, count(*) count
            FROM todo t
            JOIN session s ON t.session_id = s.id
            WHERE date(datetime(s.time_created/1000, 'unixepoch', '+9 hours')) = ?
            GROUP BY status
            """,
            (target_date,),
        )
    else:
        todo_rows = []
    hot_files = _rows(
        con,
        """
        SELECT json_extract(data, '$.state.input.filePath') file,
               count(*) edits
        FROM part
        WHERE json_extract(data, '$.type') = 'tool'
          AND json_extract(data, '$.tool') IN ('write', 'edit')
          AND json_extract(data, '$.state.input.filePath') IS NOT NULL
          AND date(datetime(time_created/1000, 'unixepoch', '+9 hours')) = ?
        GROUP BY file
        ORDER BY edits DESC, file ASC
        LIMIT 10
        """,
        (target_date,),
    )
    con.close()
    total_tokens = sum(_num(tokens.get(k)) for k in ("input", "output", "reasoning", "cache_read", "cache_write"))
    model_usage = []
    for row in model_rows:
        total = sum(_num(row.get(k)) for k in ("input", "output", "reasoning", "cache_read", "cache_write"))
        cache_miss = _num(row.get("input"))
        cache_read = _num(row.get("cache_read"))
        total_input = cache_miss + cache_read
        model_usage.append({
            "model": row.get("model"),
            "provider": row.get("provider"),
            "input": int(total_input),
            "cache_miss": int(cache_miss),
            "cache_read": int(cache_read),
            "output": int(_num(row.get("output"))),
            "reasoning": int(_num(row.get("reasoning"))),
            "cache_write": int(_num(row.get("cache_write"))),
            "total": int(total),
            "cost": round(_num(row.get("cost")), 6),
            "cache_hit_pct": _pct(cache_read, total_input),
            "messages": int(_num(row.get("messages"))),
        })
    todo_counts = {str(r.get("status")): int(_num(r.get("count"))) for r in todo_rows}
    todo_total = sum(todo_counts.values())
    todo_completed = todo_counts.get("completed", 0)
    return {
        "available": True,
        "sessions": {"total": int(_num(sessions.get("total"))), "root": int(_num(sessions.get("root"))), "subagent": int(_num(sessions.get("subagent"))), "projects": int(_num(sessions.get("projects"))), "summary_files": int(_num(sessions.get("summary_files"))), "compactions": int(_num(sessions.get("compactions")))},
        "n_turns": int(_num(turns.get("n_turns"))),
        "n_toolcalls": int(_num(tool.get("tool_calls"))),
        "error_rate": {"tool_calls": int(_num(tool.get("tool_calls"))), "tool_errors": int(_num(tool.get("tool_errors"))), "rate_pct": _pct(_num(tool.get("tool_errors")), _num(tool.get("tool_calls")))},
        "tool_schema": _tool_schema_summary([(r.get("tool"), r.get("input")) for r in tool_rows]),
        "tool_breakdown": [{"tool": r.get("tool"), "calls": int(_num(r.get("calls"))), "errors": int(_num(r.get("errors"))), "error_rate_pct": _pct(_num(r.get("errors")), _num(r.get("calls")))} for r in tool_breakdown],
        "todo": {"total": todo_total, "completed": todo_completed, "pending": todo_counts.get("pending", 0), "in_progress": todo_counts.get("in_progress", 0), "cancelled": todo_counts.get("cancelled", 0), "completion_rate_pct": _pct(todo_completed, todo_total)},
        "model_usage": model_usage,
        "hourly_sessions": [{"hour": r.get("hour"), "sessions": int(_num(r.get("sessions"))), "root": int(_num(r.get("root"))), "subagent": int(_num(r.get("subagent")))} for r in hourly],
        "projects": [{"project": r.get("project"), "path": r.get("path"), "sessions": int(_num(r.get("sessions")))} for r in project_rows],
        "hot_files": [{"file": r.get("file"), "edits": int(_num(r.get("edits")))} for r in hot_files],
        "tokens": {"input": int(_num(tokens.get("input"))), "output": int(_num(tokens.get("output"))), "reasoning": int(_num(tokens.get("reasoning"))), "cache_read": int(_num(tokens.get("cache_read"))), "cache_write": int(_num(tokens.get("cache_write"))), "total": int(total_tokens)},
        "latency": {"avg_session_sec": round(_num(sessions.get("avg_session_sec")), 2), "max_session_sec": round(_num(sessions.get("max_session_sec")), 2)},
        "cost": {"recorded_usd": round(_num(tokens.get("recorded_usd")), 6), "cost_per_session_usd": round(_num(tokens.get("recorded_usd")) / _num(sessions.get("total")), 6) if _num(sessions.get("total")) else None},
    }

def _collect_hermes(target_date: str, db_path: Path) -> dict[str, Any]:
    con = _connect(db_path)
    if con is None:
        return {"available": False, "reason": f"missing db: {db_path}"}
    sessions = _one(
        con,
        """
        SELECT count(*) root,
               coalesce(sum(ended_at IS NULL), 0) zombie,
               coalesce(sum(tool_call_count), 0) toolcalls,
               coalesce(sum(message_count), 0) turns,
               coalesce(sum(input_tokens), 0) input,
               coalesce(sum(output_tokens), 0) output,
               coalesce(sum(cache_read_tokens), 0) cache_read,
               coalesce(sum(cache_write_tokens), 0) cache_write,
               coalesce(sum(reasoning_tokens), 0) reasoning,
               coalesce(sum(coalesce(actual_cost_usd, estimated_cost_usd, 0)), 0) cost,
               avg(CASE WHEN ended_at IS NOT NULL THEN ended_at - started_at END) avg_session_sec,
               max(CASE WHEN ended_at IS NOT NULL THEN ended_at - started_at END) max_session_sec
        FROM sessions
        WHERE parent_session_id IS NULL
          AND date(datetime(started_at, 'unixepoch', '+9 hours')) = ?
        """,
        (target_date,),
    )
    model_rows = _rows(
        con,
        """
        SELECT coalesce(model, 'unknown') model,
               coalesce(billing_provider, 'unknown') provider,
               count(*) sessions,
               coalesce(sum(input_tokens), 0) input,
               coalesce(sum(output_tokens), 0) output,
               coalesce(sum(cache_read_tokens), 0) cache_read,
               coalesce(sum(cache_write_tokens), 0) cache_write,
               coalesce(sum(reasoning_tokens), 0) reasoning,
               coalesce(sum(coalesce(actual_cost_usd, estimated_cost_usd, 0)), 0) cost
        FROM sessions
        WHERE parent_session_id IS NULL
          AND date(datetime(started_at, 'unixepoch', '+9 hours')) = ?
        GROUP BY 1, 2
        ORDER BY (input + output + cache_read + cache_write + reasoning) DESC
        """,
        (target_date,),
    )
    source_rows = _rows(
        con,
        """
        SELECT source, count(*) sessions
        FROM sessions
        WHERE parent_session_id IS NULL
          AND date(datetime(started_at, 'unixepoch', '+9 hours')) = ?
        GROUP BY source
        ORDER BY sessions DESC, source ASC
        """,
        (target_date,),
    )
    end_reason_rows = _rows(
        con,
        """
        SELECT coalesce(end_reason, 'NULL') end_reason, count(*) sessions
        FROM sessions
        WHERE parent_session_id IS NULL
          AND date(datetime(started_at, 'unixepoch', '+9 hours')) = ?
        GROUP BY end_reason
        ORDER BY sessions DESC, end_reason ASC
        """,
        (target_date,),
    )
    hourly = _rows(
        con,
        """
        SELECT strftime('%H', datetime(started_at, 'unixepoch', '+9 hours')) hour,
               count(*) sessions
        FROM sessions
        WHERE parent_session_id IS NULL
          AND date(datetime(started_at, 'unixepoch', '+9 hours')) = ?
        GROUP BY hour
        ORDER BY hour
        """,
        (target_date,),
    )
    message_schema = _rows(con, "PRAGMA table_info(messages)", ())
    has_tool_calls = any(row.get("name") == "tool_calls" for row in message_schema)
    calls: list[tuple[str | None, Any]] = []
    if has_tool_calls:
        for row in _rows(
            con,
            """
            SELECT tool_calls
            FROM messages
            WHERE tool_calls IS NOT NULL
              AND date(datetime(timestamp, 'unixepoch', '+9 hours')) = ?
            """,
            (target_date,),
        ):
            try:
                entries = json.loads(row.get("tool_calls") or "[]")
            except json.JSONDecodeError:
                entries = []
            for entry in entries if isinstance(entries, list) else []:
                fn = entry.get("function", {}) if isinstance(entry, dict) else {}
                calls.append((fn.get("name"), fn.get("arguments")))
    con.close()
    total_tokens = sum(_num(sessions.get(k)) for k in ("input", "output", "reasoning", "cache_read", "cache_write"))
    model_usage = []
    for row in model_rows:
        cache_miss = _num(row.get("input"))
        cache_read = _num(row.get("cache_read"))
        total_input = cache_miss + cache_read
        total = sum(_num(row.get(k)) for k in ("input", "output", "reasoning", "cache_read", "cache_write"))
        model_usage.append({
            "model": row.get("model"),
            "provider": row.get("provider"),
            "sessions": int(_num(row.get("sessions"))),
            "input": int(total_input),
            "cache_miss": int(cache_miss),
            "cache_read": int(cache_read),
            "output": int(_num(row.get("output"))),
            "reasoning": int(_num(row.get("reasoning"))),
            "cache_write": int(_num(row.get("cache_write"))),
            "total": int(total),
            "cost": round(_num(row.get("cost")), 6),
            "cache_hit_pct": _pct(cache_read, total_input),
        })
    return {
        "available": True,
        "sessions": {"root": int(_num(sessions.get("root"))), "zombie": int(_num(sessions.get("zombie")))},
        "n_turns": int(_num(sessions.get("turns"))),
        "n_toolcalls": int(_num(sessions.get("toolcalls"))),
        "error_rate": {"tool_calls": int(_num(sessions.get("toolcalls"))), "tool_errors": None, "rate_pct": None},
        "tool_schema": _tool_schema_summary(calls),
        "model_usage": model_usage,
        "source_distribution": [{"source": r.get("source"), "sessions": int(_num(r.get("sessions")))} for r in source_rows],
        "end_reason_distribution": [{"end_reason": r.get("end_reason"), "sessions": int(_num(r.get("sessions")))} for r in end_reason_rows],
        "hourly_sessions": [{"hour": r.get("hour"), "sessions": int(_num(r.get("sessions")))} for r in hourly],
        "tokens": {"input": int(_num(sessions.get("input"))), "output": int(_num(sessions.get("output"))), "reasoning": int(_num(sessions.get("reasoning"))), "cache_read": int(_num(sessions.get("cache_read"))), "cache_write": int(_num(sessions.get("cache_write"))), "total": int(total_tokens)},
        "latency": {"avg_session_sec": round(_num(sessions.get("avg_session_sec")), 2), "max_session_sec": round(_num(sessions.get("max_session_sec")), 2)},
        "cost": {"recorded_usd": round(_num(sessions.get("cost")), 6), "cost_per_session_usd": round(_num(sessions.get("cost")) / _num(sessions.get("root")), 6) if _num(sessions.get("root")) else None},
    }
