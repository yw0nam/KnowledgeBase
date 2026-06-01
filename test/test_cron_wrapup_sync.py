"""Regression tests for cron-wrapup's shell-level data-sync handoff."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import kb

WRAPPER = kb.REPO_ROOT / "scripts" / "cron" / "kb-cron-wrapup.sh"


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(cwd), *args],
        check=True,
        capture_output=True,
        text=True,
    )


def _write_executable(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    path.chmod(0o755)


def _make_root(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "kb"
    data = root / "data"
    data.mkdir(parents=True)
    _git(data, "init", "-q", "-b", "master")
    _git(data, "config", "user.email", "t@t")
    _git(data, "config", "user.name", "t")
    (data / "log.md").write_text("# log\n")
    _git(data, "add", "-A")
    _git(data, "commit", "-qm", "init")

    bin_dir = root / "bin"
    _write_executable(bin_dir / "opencode", "#!/bin/sh\nexit 0\n")
    _write_executable(
        root / ".claude" / "skills" / "data-sync" / "scripts" / "sync-data.sh",
        """#!/bin/sh
count="$(cat "$SYNC_COUNT" 2>/dev/null || echo 0)"
count=$((count + 1))
printf '%s\n' "$count" > "$SYNC_COUNT"
printf 'fake sync %s\n' "$count"
exit "${SYNC_EXIT:-0}"
""",
    )
    return root, bin_dir


def _run(root: Path, bin_dir: Path, *, sync_exit: str) -> subprocess.CompletedProcess:
    env = dict(
        os.environ,
        KB_ROOT_OVERRIDE=str(root),
        PATH=f"{bin_dir}:{os.environ['PATH']}",
        SYNC_COUNT=str(root / "sync-count"),
        SYNC_EXIT=sync_exit,
    )
    return subprocess.run(["bash", str(WRAPPER)], capture_output=True, text=True, env=env)


def test_cron_wrapup_persists_sync_failure_and_exits_nonzero(tmp_path):
    root, bin_dir = _make_root(tmp_path)
    proc = _run(root, bin_dir, sync_exit="17")
    assert proc.returncode == 17

    archives = list((root / "data" / "raw" / "ops" / "cron").rglob("*_kb-cron-wrapup.log"))
    assert len(archives) == 1
    archive_rel = archives[0].relative_to(root / "data")
    committed = _git(root / "data", "show", f"HEAD:{archive_rel}").stdout
    assert "fake sync 1" in committed
    assert "SYNC_SKIPPED: sync-data.sh exited non-zero (rc=17)" in committed


def test_cron_wrapup_publishes_archived_log_after_success(tmp_path):
    root, bin_dir = _make_root(tmp_path)
    proc = _run(root, bin_dir, sync_exit="0")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert (root / "sync-count").read_text().strip() == "2"

