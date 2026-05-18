from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from kb_mcp.cli.hermes_daily_report import (
    collect_metrics as collect_hermes_metrics,
    render_report as render_hermes_report,
)
from kb_mcp.cli.opencode_daily_report import (
    collect_metrics as collect_opencode_metrics,
    render_report as render_opencode_report,
)


def make_opencode_db(path: Path) -> None:
    con = sqlite3.connect(path)
    con.executescript("""
        CREATE TABLE project (id text PRIMARY KEY, worktree text, name text, time_created integer, time_updated integer);
        CREATE TABLE session (
            id text PRIMARY KEY,
            project_id text NOT NULL,
            parent_id text,
            title text NOT NULL,
            directory text NOT NULL,
            time_created integer NOT NULL,
            time_updated integer NOT NULL,
            summary_files INTEGER DEFAULT 0,
            time_compacting INTEGER,
            model TEXT
        );
        CREATE TABLE message (id text PRIMARY KEY, session_id text NOT NULL, time_created integer NOT NULL, time_updated integer NOT NULL, data text NOT NULL);
        CREATE TABLE part (id text PRIMARY KEY, message_id text NOT NULL, session_id text NOT NULL, time_created integer NOT NULL, time_updated integer NOT NULL, data text NOT NULL);
        """)
    # 2026-05-14 01:00 KST == 2026-05-13 16:00 UTC in ms.
    t = 1778688000000
    con.execute("INSERT INTO project VALUES ('p1', '/repo', 'repo', ?, ?)", (t, t))
    con.execute(
        "INSERT INTO session VALUES ('s1', 'p1', NULL, 'root', '/repo', ?, ?, 1, NULL, 'claude-sonnet-4-6')",
        (t, t + 60000),
    )
    con.execute(
        "INSERT INTO session VALUES ('s2', 'p1', 's1', 'sub', '/repo', ?, ?, 0, NULL, 'claude-sonnet-4-6')",
        (t + 1000, t + 31000),
    )
    con.execute(
        "INSERT INTO message VALUES ('m1', 's1', ?, ?, ?)",
        (
            t,
            t,
            json.dumps(
                {
                    "role": "assistant",
                    "modelID": "claude-sonnet-4-6",
                    "providerID": "anthropic",
                    "tokens": {
                        "input": 10,
                        "output": 5,
                        "reasoning": 2,
                        "cache": {"read": 90, "write": 3},
                    },
                    "cost": 0.12,
                }
            ),
        ),
    )
    con.execute(
        "INSERT INTO message VALUES ('m2', 's1', ?, ?, ?)",
        (t, t, json.dumps({"role": "user"})),
    )
    con.execute(
        "INSERT INTO part VALUES ('pt1', 'm1', 's1', ?, ?, ?)",
        (
            t,
            t,
            json.dumps(
                {
                    "type": "tool",
                    "tool": "bash",
                    "state": {"status": "completed", "input": {"command": "pwd"}},
                }
            ),
        ),
    )
    con.execute(
        "INSERT INTO part VALUES ('pt2', 'm1', 's1', ?, ?, ?)",
        (
            t,
            t,
            json.dumps(
                {
                    "type": "tool",
                    "tool": "read",
                    "state": {
                        "status": "error",
                        "input": {"filePath": "x", "bogus": True},
                    },
                }
            ),
        ),
    )
    con.commit()
    con.close()


def make_hermes_db(path: Path) -> None:
    con = sqlite3.connect(path)
    con.executescript("""
        CREATE TABLE sessions (
            id TEXT PRIMARY KEY,
            source TEXT NOT NULL,
            model TEXT,
            parent_session_id TEXT,
            started_at REAL NOT NULL,
            ended_at REAL,
            end_reason TEXT,
            message_count INTEGER DEFAULT 0,
            tool_call_count INTEGER DEFAULT 0,
            input_tokens INTEGER DEFAULT 0,
            output_tokens INTEGER DEFAULT 0,
            cache_read_tokens INTEGER DEFAULT 0,
            cache_write_tokens INTEGER DEFAULT 0,
            reasoning_tokens INTEGER DEFAULT 0,
            actual_cost_usd REAL,
            estimated_cost_usd REAL,
            billing_provider TEXT
        );
        CREATE TABLE messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT,
            tool_calls TEXT,
            tool_name TEXT,
            timestamp REAL NOT NULL
        );
        """)
    # 2026-05-14 01:00 KST in seconds.
    t = 1778688000
    con.execute(
        "INSERT INTO sessions VALUES ('h1', 'cron', 'gpt-5.5', NULL, ?, ?, 'cron_complete', 4, 2, 100, 20, 300, 0, 5, 0.5, NULL, 'custom')",
        (t, t + 120),
    )
    con.execute(
        "INSERT INTO messages(session_id, role, content, tool_calls, tool_name, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
        (
            "h1",
            "assistant",
            "",
            json.dumps(
                [
                    {
                        "type": "function",
                        "function": {
                            "name": "terminal",
                            "arguments": json.dumps({"command": "date", "extra": 1}),
                        },
                    }
                ]
            ),
            None,
            t,
        ),
    )
    con.commit()
    con.close()


def test_collect_split_usage_metrics_counts_non_deferred_metrics(tmp_path):
    opencode_db = tmp_path / "opencode.db"
    hermes_db = tmp_path / "state.db"
    make_opencode_db(opencode_db)
    make_hermes_db(hermes_db)

    opencode_metrics = collect_opencode_metrics("2026-05-14", opencode_db)
    hermes_metrics = collect_hermes_metrics("2026-05-14", hermes_db)

    assert opencode_metrics["deferred_metrics"] == [
        "Task Completion Rate",
        "pass@k",
        "pass^k",
    ]
    assert opencode_metrics["opencode"]["sessions"]["total"] == 2
    assert opencode_metrics["opencode"]["sessions"]["root"] == 1
    assert opencode_metrics["opencode"]["error_rate"]["tool_errors"] == 1
    assert opencode_metrics["opencode"]["error_rate"]["tool_calls"] == 2
    assert opencode_metrics["opencode"]["tool_schema"]["invalid_calls"] == 1
    assert opencode_metrics["opencode"]["n_turns"] == 2
    assert opencode_metrics["opencode"]["tokens"]["total"] == 110
    assert opencode_metrics["opencode"]["cost"]["recorded_usd"] == 0.12
    assert hermes_metrics["hermes"]["sessions"]["root"] == 1
    assert hermes_metrics["hermes"]["tool_schema"]["invalid_calls"] == 1
    assert hermes_metrics["hermes"]["latency"]["avg_session_sec"] == 120


def test_render_split_daily_reports_use_fixed_evaluation_layout(tmp_path):
    opencode_db = tmp_path / "opencode.db"
    hermes_db = tmp_path / "state.db"
    make_opencode_db(opencode_db)
    make_hermes_db(hermes_db)
    opencode_metrics = collect_opencode_metrics("2026-05-14", opencode_db)
    hermes_metrics = collect_hermes_metrics("2026-05-14", hermes_db)

    opencode_report = render_opencode_report(opencode_metrics)
    hermes_report = render_hermes_report(hermes_metrics)

    for report in (opencode_report, hermes_report):
        assert "## Development/Evaluation Metrics" in report
        assert "| Error Rate |" in report
        assert "| Hallucinated Parameters |" in report
        assert "| n_toolcalls / n_turns |" in report
        assert "| Policy Compliance Rate |" in report
        assert "Task Completion Rate" in report
        assert report.count("## Development/Evaluation Metrics") == 1
