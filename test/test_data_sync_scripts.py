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


def test_workbranch_migrates_master_onto_workbranch(tmp_path):
    # remote (bare) + a clone on master ahead by 1 commit
    bare = tmp_path / "remote.git"
    subprocess.run(
        ["git", "init", "-q", "--bare", "-b", "master", str(bare)], check=True
    )
    data = _make_data_repo(tmp_path)
    _git(data, "remote", "add", "origin", str(bare))
    _git(data, "push", "-q", "-u", "origin", "master")
    # local master now 1 ahead of origin/master
    (data / "log.md").write_text("# log\nahead\n")
    _git(data, "commit", "-qam", "ahead")

    proc = _run("setup-data-workbranch.sh", data, KB_SYNC_TEST="1")
    assert proc.returncode == 0, proc.stderr
    head = subprocess.run(
        ["git", "-C", str(data), "symbolic-ref", "--short", "HEAD"],
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert head.startswith("sync/")
    # .sync-machine-id is machine-local and must not pollute git status
    assert (data / ".sync-machine-id").exists()
    porcelain = subprocess.run(
        ["git", "-C", str(data), "status", "--porcelain"],
        capture_output=True,
        text=True,
    ).stdout
    assert ".sync-machine-id" not in porcelain
    # local master mirrors origin/master (the ahead commit moved to the work branch)
    master = subprocess.run(
        ["git", "-C", str(data), "rev-parse", "master"], capture_output=True, text=True
    ).stdout.strip()
    origin_master = subprocess.run(
        ["git", "-C", str(data), "rev-parse", "origin/master"],
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert master == origin_master
    # idempotent: a second run is a no-op (already on a work branch)
    proc2 = _run("setup-data-workbranch.sh", data, KB_SYNC_TEST="1")
    assert proc2.returncode == 0
    assert "already on a work branch" in (proc2.stdout + proc2.stderr)


def test_ci_install_refuses_on_workbranch(tmp_path):
    data = _make_data_repo(
        tmp_path, origin_url="git@github.com:yw0nam/PrivateKnowledgeBase.git"
    )
    _git(data, "checkout", "-q", "-b", "sync/host-2026-05-29-abcd")
    proc = _run("setup-data-ci.sh", data, "deadbeef", KB_SYNC_TEST="1")
    assert proc.returncode != 0
    blob = (proc.stdout + proc.stderr).lower()
    assert "must run on" in blob or "work branch" in blob


def test_ci_install_substitutes_pin_and_is_idempotent(tmp_path):
    bare = tmp_path / "remote.git"
    subprocess.run(
        ["git", "init", "-q", "--bare", "-b", "master", str(bare)], check=True
    )
    data = _make_data_repo(tmp_path)
    _git(data, "remote", "add", "origin", str(bare))
    _git(data, "push", "-q", "-u", "origin", "master")
    proc = _run("setup-data-ci.sh", data, "v1.2.3", KB_SYNC_TEST="1")
    assert proc.returncode == 0, proc.stderr
    wf = (data / ".github" / "workflows" / "lint.yml").read_text()
    assert "yw0nam/KnowledgeBase@v1.2.3" in wf
    assert "__KB_PIN__" not in wf
    # idempotent: second run no new commit
    proc2 = _run("setup-data-ci.sh", data, "v1.2.3", KB_SYNC_TEST="1")
    assert proc2.returncode == 0
    assert "no-op" in (proc2.stdout + proc2.stderr).lower()
