"""Contract tests for the `wiki-note` skill.

The skill writes first-party pages (`origin: authored`, `sources: []`, born
`approved`) and resolves the KB root from its global symlink so it works from any
repo. These tests lock both behaviors so a future lint change or skill edit can't
silently break it.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import kb.cli.lint_wiki as lint_mod
from kb.cli.wiki_index import INDEX_FILENAME, build_index

# The KB-root resolver embedded in .claude/skills/wiki-note/SKILL.md (Step 1).
# Kept in sync with the skill; this test is the guard that it actually resolves.
RESOLVER = r"""
KB_ROOT="${KB_ROOT:-}"
if [ -z "$KB_ROOT" ] && [ -L "$HOME/.claude/skills/wiki-note" ]; then
  KB_ROOT="$(cd "$(dirname "$(readlink -f "$HOME/.claude/skills/wiki-note")")/../.." && pwd)"
fi
[ -n "$KB_ROOT" ] || KB_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
[ -d "$KB_ROOT/data/wiki" ] || { echo "KB root not found"; exit 1; }
echo "$KB_ROOT"
"""

AUTHORED_FM = """\
---
type: concept
origin: authored
review_status: approved
created: "2026-06-02"
updated: "2026-06-02"
sources: []
aliases: []
tags: [first-party]
---
"""


def _make_wiki_root(tmp_path: Path) -> Path:
    wiki = tmp_path / "wiki"
    for sub in ("entities", "concepts", "decisions", "summaries", "questions"):
        (wiki / sub).mkdir(parents=True, exist_ok=True)
    return wiki


def test_authored_page_with_empty_sources_lints_clean(tmp_path):
    """A first-party page (origin: authored, sources: []) must lint with 0 errors.

    This is the contract wiki-note relies on: empty sources is allowed, and the
    extra `origin` key is accepted (lint has no allowed-keys allowlist).
    """
    wiki = _make_wiki_root(tmp_path)
    body = "# Local lint must mirror CI\n\nA pre-merge lint that checks the working tree is not a faithful proxy for CI that checks the committed tree. Gate on a clean, fully-committed tree.\n"
    (wiki / "concepts" / "local-lint-mirrors-ci.md").write_text(
        AUTHORED_FM + "\n" + body
    )

    # Mirror the real workflow: regenerate INDEX.md before linting.
    (wiki / INDEX_FILENAME).write_text(build_index(wiki))

    result = lint_mod.LintResult()
    lint_mod.lint(result, wiki_dir=wiki)

    assert result.errors == [], f"expected 0 errors, got: {result.errors}"


def test_kb_root_resolves_from_global_symlink(tmp_path):
    """The Step-1 resolver derives KB root from the wiki-note global symlink."""
    fake_home = tmp_path / "home"
    kb_root = tmp_path / "KnowledgeBase"
    # Real skill dir inside the KB repo + the data/wiki marker the resolver checks.
    (kb_root / ".claude" / "skills" / "wiki-note").mkdir(parents=True)
    (kb_root / "data" / "wiki").mkdir(parents=True)
    # Global symlink: ~/.claude/skills/wiki-note -> <KB_ROOT>/.claude/skills/wiki-note
    (fake_home / ".claude" / "skills").mkdir(parents=True)
    os.symlink(
        kb_root / ".claude" / "skills" / "wiki-note",
        fake_home / ".claude" / "skills" / "wiki-note",
    )

    env = dict(os.environ, HOME=str(fake_home))
    env.pop("KB_ROOT", None)
    proc = subprocess.run(
        ["bash", "-c", RESOLVER],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(tmp_path),
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == str(kb_root)


def test_kb_root_env_override_wins(tmp_path):
    """An explicit $KB_ROOT short-circuits symlink resolution."""
    kb_root = tmp_path / "explicit"
    (kb_root / "data" / "wiki").mkdir(parents=True)
    env = dict(os.environ, HOME=str(tmp_path / "nohome"), KB_ROOT=str(kb_root))
    proc = subprocess.run(
        ["bash", "-c", RESOLVER], capture_output=True, text=True, env=env
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == str(kb_root)
