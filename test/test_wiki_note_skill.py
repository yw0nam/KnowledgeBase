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

from alembic import command
from alembic.config import Config
from sqlalchemy.orm import Session

from kb import REPO_ROOT
from kb.db import make_engine, make_session_factory
from kb.lint.wiki import validate_page_create

RESOLVER = r"""
KB_ROOT="${KB_ROOT:-}"
if [ -z "$KB_ROOT" ] && [ -L "$HOME/.claude/skills/wiki-note" ]; then
  KB_ROOT="$(cd "$(dirname "$(readlink -f "$HOME/.claude/skills/wiki-note")")/../.." && pwd)"
fi
[ -n "$KB_ROOT" ] || KB_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
[ -d "$KB_ROOT/data/wiki" ] || { echo "KB root not found"; exit 1; }
echo "$KB_ROOT"
"""

AUTHORED_FM = {
    "type": "concept",
    "origin": "authored",
    "review_status": "approved",
    "created": "2026-06-02",
    "updated": "2026-06-02",
    "sources": [],
    "aliases": [],
    "tags": ["first-party"],
}


def _make_session(tmp_path: Path) -> Session:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "alembic"))
    import os as _os

    _os.environ["KB_DATA_DIR"] = str(data_dir)
    command.upgrade(cfg, "head")
    engine = make_engine(data_dir)
    session_factory = make_session_factory(engine)
    return session_factory()


def test_authored_page_with_empty_sources_lints_clean(tmp_path):
    """A first-party page (origin: authored, sources: []) must lint with 0 errors."""
    session = _make_session(tmp_path)
    body = "# Local lint must mirror CI\n\nA pre-merge lint that checks the working tree is not a faithful proxy for CI that checks the committed tree. Gate on a clean, fully-committed tree.\n"

    result = validate_page_create(
        AUTHORED_FM, body, session, slug="local-lint-mirrors-ci"
    )
    session.close()

    assert result.ok, f"expected 0 errors, got: {result.errors}"


def test_kb_root_resolves_from_global_symlink(tmp_path):
    """The Step-1 resolver derives KB root from the wiki-note global symlink."""
    fake_home = tmp_path / "home"
    kb_root = tmp_path / "KnowledgeBase"
    (kb_root / ".claude" / "skills" / "wiki-note").mkdir(parents=True)
    (kb_root / "data" / "wiki").mkdir(parents=True)
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
