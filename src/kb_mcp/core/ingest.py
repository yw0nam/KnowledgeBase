"""Subprocess wrapper around scripts/ingest-github.sh."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Sequence


REPO_PATTERN = re.compile(r"^[\w.-]+/[\w.-]+$")
DEFAULT_SCRIPT_PATH = Path("scripts/ingest-github.sh")


def _validate_repos(repos: Sequence[str]) -> None:
    if not repos:
        raise ValueError("repos must not be empty; pass at least one 'owner/repo'")
    for r in repos:
        if not REPO_PATTERN.match(r):
            raise ValueError(
                f"invalid repo {r!r}; expected 'owner/repo' format"
            )


def ingest_github(
    repos: Sequence[str],
    script_path: str | Path | None = None,
    cwd: str | Path | None = None,
    timeout: float | None = 600.0,
) -> dict:
    _validate_repos(repos)

    path = Path(script_path) if script_path is not None else DEFAULT_SCRIPT_PATH
    if not path.exists():
        raise FileNotFoundError(f"ingest script not found at {path}")

    cmd = [str(path), *repos]
    result = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return {
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "repos": list(repos),
    }
