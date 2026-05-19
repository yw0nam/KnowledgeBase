"""Subcommand implementations for kb-wiki-review.

Each cmd_* function takes a wiki_dir Path plus stem/args and returns
an int exit code. Errors are printed to stderr via _err().
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from kb_mcp.cli.wiki_review import _feedback, _store


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


def cmd_approve(wiki_dir: Path, stem: str, feedback: str, today: str) -> int:
    """pending_for_approve → approved."""
    path = _resolve_or_print(wiki_dir, stem)
    if path is None:
        return 1
    current = _store.get_frontmatter_field(path, "review_status")
    if current == "approved":
        _err(f"already approved: {stem}")
        return 1
    if current != "pending_for_approve":
        _err(
            f"must be pending_for_approve (current: {current!r}); "
            "run promote first"
        )
        return 1
    _store.set_frontmatter_field(path, "review_status", "approved")
    _feedback.append_feedback_line(path, today, "Approved", feedback)
    print(f"✓ Approved: {path.relative_to(wiki_dir)}")
    return 0


def cmd_reject(
    wiki_dir: Path,
    rejected_dir: Path,
    data_dir: Path,
    stem: str,
    feedback: str,
    today: str,
    now_iso: str,
    rejected_by: str,
) -> int:
    """pending_for_approve → rejected (file moved out of wiki/ via git mv).

    ``rejected_by`` is ``"user"`` for interactive reject and ``"auto_ttl"`` for
    ttl-sweep auto-rejection. ``feedback`` is the User Feedback line text
    (empty for system actions skips the body append).
    ``today`` is KST-local YYYY-MM-DD; ``now_iso`` is ISO timestamp with
    timezone offset.
    """
    path = _resolve_or_print(wiki_dir, stem)
    if path is None:
        return 1
    current = _store.get_frontmatter_field(path, "review_status")
    if current == "rejected":
        _err(f"already rejected: {stem}")
        return 1
    if current != "pending_for_approve" and rejected_by == "user":
        _err(
            f"must be pending_for_approve (current: {current!r}); "
            "user reject not allowed from this state"
        )
        return 1
    if current != "not_processed" and rejected_by == "auto_ttl":
        # auto_ttl should only reach files in not_processed state — caller bug.
        _err(f"ttl-sweep target must be not_processed (current: {current!r})")
        return 1

    rel = path.relative_to(wiki_dir)
    dest = rejected_dir / rel
    if dest.exists():
        _err(
            f"rejection target already exists at "
            f"{dest.relative_to(data_dir)}; resolve manually"
        )
        return 1

    dest.parent.mkdir(parents=True, exist_ok=True)

    # Step 1: update frontmatter + body BEFORE the move so git tracks the
    # rename + modification as a single change.
    _store.set_frontmatter_field(path, "review_status", "rejected")
    _store.add_frontmatter_lines(
        path,
        [f'rejected_at: "{now_iso}"', f"rejected_by: {rejected_by}"],
    )
    label = "Auto-rejected" if rejected_by == "auto_ttl" else "Rejected"
    _feedback.append_feedback_line(path, today, label, feedback)

    # Step 2: git mv. cwd = data_dir so paths are relative to repo root.
    src_rel = path.relative_to(data_dir)
    dest_rel = dest.relative_to(data_dir)
    try:
        subprocess.run(
            ["git", "mv", str(src_rel), str(dest_rel)],
            cwd=data_dir,
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        _err(f"git mv failed: {exc.stderr.strip()}")
        return 1

    print(f"✓ Rejected: {rel} → {dest.relative_to(data_dir)}")
    return 0
