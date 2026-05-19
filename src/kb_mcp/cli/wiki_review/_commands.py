"""Subcommand implementations for kb-wiki-review.

Each cmd_* function takes a wiki_dir Path plus stem/args and returns
an int exit code. Errors are printed to stderr via _err().
"""

from __future__ import annotations

import sys
from pathlib import Path

from kb_mcp.cli.wiki_review import _store


def _err(msg: str) -> None:
    print(msg, file=sys.stderr)


def _resolve_or_print(wiki_dir: Path, stem: str) -> Path | None:
    """Resolve stem to file path; print error and return None on failure."""
    try:
        return _store.resolve_stem(wiki_dir, stem)
    except _store.PageNotFound:
        _err(f"page not found in wiki/: {stem}")
        return None
    except _store.StemCollision as exc:
        _err(str(exc))
        return None


def cmd_promote(wiki_dir: Path, stem: str) -> int:
    """not_processed → pending_for_approve."""
    path = _resolve_or_print(wiki_dir, stem)
    if path is None:
        return 1
    current = _store.get_frontmatter_field(path, "review_status")
    if current != "not_processed":
        _err(f"promote only from not_processed (current: {current!r})")
        return 1
    _store.set_frontmatter_field(path, "review_status", "pending_for_approve")
    print(f"✓ Promoted: {path.relative_to(wiki_dir)}")
    return 0
