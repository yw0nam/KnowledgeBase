"""Subprocess tests: kb-lint runs end-to-end against DATABASE_URL (Postgres)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def _run(target: str, database_url: str, data_dir: Path) -> subprocess.CompletedProcess:
    env = dict(os.environ, DATABASE_URL=database_url, KB_DATA_DIR=str(data_dir))
    return subprocess.run(
        [sys.executable, "-m", "kb.cli.lint", target],
        capture_output=True,
        text=True,
        env=env,
    )


def test_lint_all_passes_on_empty_db(database_url, data_dir):
    """kb-lint all on a freshly-migrated (empty) DB passes with 0 errors."""
    proc = _run("all", database_url, data_dir)
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert "PASSED" in proc.stdout


def test_lint_wiki_passes_on_empty_db(database_url, data_dir):
    """kb-lint wiki resolves DATABASE_URL and runs on the target DB."""
    proc = _run("wiki", database_url, data_dir)
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert "PASSED" in proc.stdout


def test_lint_handoff_passes_on_empty_db(database_url, data_dir):
    """kb-lint handoff resolves DATABASE_URL and runs on the target DB."""
    proc = _run("handoff", database_url, data_dir)
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert "PASSED" in proc.stdout
