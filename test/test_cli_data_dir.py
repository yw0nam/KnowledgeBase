"""Subprocess tests: the CLIs target KB_DATA_DIR, not the repo default."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def _run(module: str, data_dir: Path) -> subprocess.CompletedProcess:
    env = dict(os.environ, KB_DATA_DIR=str(data_dir))
    return subprocess.run(
        [sys.executable, "-m", module],
        capture_output=True,
        text=True,
        env=env,
    )


def _make_wiki(root: Path) -> None:
    for sub in ("entities", "concepts", "decisions", "questions",
                "improvements", "checklists", "summaries"):
        (root / "wiki" / sub).mkdir(parents=True, exist_ok=True)
    (root / "raw").mkdir(parents=True, exist_ok=True)


def test_lint_wiki_lints_kb_data_dir(tmp_path):
    _make_wiki(tmp_path)
    # A page with a dead wikilink → a deterministic ERROR proving the lint
    # read THIS tree (not the repo's real data/).
    page = tmp_path / "wiki" / "concepts" / "Bad.md"
    page.write_text(
        '---\ntype: concept\nreview_status: approved\n'
        'created: "2026-05-01"\nupdated: "2026-05-01"\nsources: []\ntags: []\n---\n\n'
        "Body links to [[NonexistentTarget]].\n"
    )
    proc = _run("kb.cli.lint_wiki", tmp_path)
    assert proc.returncode == 1
    assert "dead link [[NonexistentTarget]]" in proc.stdout
