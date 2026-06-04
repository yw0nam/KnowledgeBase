"""Subprocess tests: kb-lint CLI targets KB_DATA_DIR, not the repo default."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config

from kb import REPO_ROOT


def _init_db(data_dir: Path) -> None:
    """Run Alembic migrations to create an empty DB."""
    data_dir.mkdir(parents=True, exist_ok=True)
    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "alembic"))
    os.environ["KB_DATA_DIR"] = str(data_dir)
    command.upgrade(cfg, "head")


def _run(target: str, data_dir: Path) -> subprocess.CompletedProcess:
    env = dict(os.environ, KB_DATA_DIR=str(data_dir))
    return subprocess.run(
        [sys.executable, "-m", "kb.cli.lint", target],
        capture_output=True,
        text=True,
        env=env,
    )


def test_lint_all_targets_kb_data_dir(tmp_path):
    """kb-lint all on an empty DB should pass with 0 errors."""
    data_dir = tmp_path / "data"
    _init_db(data_dir)
    proc = _run("all", data_dir)
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert "PASSED" in proc.stdout


def test_lint_wiki_targets_kb_data_dir(tmp_path):
    """kb-lint wiki resolves KB_DATA_DIR and runs on the target DB."""
    data_dir = tmp_path / "data"
    _init_db(data_dir)
    proc = _run("wiki", data_dir)
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert "PASSED" in proc.stdout


def test_lint_handoff_targets_kb_data_dir(tmp_path):
    """kb-lint handoff resolves KB_DATA_DIR and runs on the target DB."""
    data_dir = tmp_path / "data"
    _init_db(data_dir)
    proc = _run("handoff", data_dir)
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert "PASSED" in proc.stdout
