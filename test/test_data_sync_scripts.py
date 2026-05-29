"""Subprocess tests for the data-sync bash scripts (guards, dry-run)."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import kb

SCRIPTS = kb.REPO_ROOT / ".claude" / "skills" / "data-sync" / "scripts"


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True
    )


def _make_data_repo(tmp_path: Path, origin_url: str | None = None) -> Path:
    """A bare-bones nested data/ repo on master."""
    data = tmp_path / "data"
    data.mkdir()
    _git(data, "init", "-q", "-b", "master")
    _git(data, "config", "user.email", "t@t")
    _git(data, "config", "user.name", "t")
    (data / "log.md").write_text("# log\n")
    _git(data, "add", "-A")
    _git(data, "commit", "-q", "-m", "init")
    if origin_url:
        _git(data, "remote", "add", "origin", origin_url)
    return data


def _run(
    script: str, data: Path, *args: str, **env_extra: str
) -> subprocess.CompletedProcess:
    # Inherit the real env (git needs HOME/PATH etc.); override the data dir.
    env = dict(os.environ, KB_DATA_OVERRIDE=str(data), **env_extra)
    return subprocess.run(
        ["bash", str(SCRIPTS / script), *args],
        capture_output=True,
        text=True,
        env=env,
    )


def test_remote_refuses_non_private_origin(tmp_path):
    data = _make_data_repo(
        tmp_path, origin_url="https://github.com/yw0nam/KnowledgeBase.git"
    )
    proc = _run(
        "setup-data-remote.sh", data, "https://github.com/yw0nam/KnowledgeBase.git"
    )
    assert proc.returncode != 0
    assert "not the allowed private remote" in (proc.stdout + proc.stderr)


def test_remote_refuses_when_origin_mismatches(tmp_path):
    data = _make_data_repo(tmp_path, origin_url="git@github.com:someone/Other.git")
    proc = _run(
        "setup-data-remote.sh", data, "git@github.com:yw0nam/PrivateKnowledgeBase.git"
    )
    assert proc.returncode != 0
    assert "already set to a different url" in (proc.stdout + proc.stderr)
