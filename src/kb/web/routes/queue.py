"""GET /api/queue — pages currently awaiting human review.

Returns every wiki page with `review_status: pending_for_approve`.
Each entry carries full frontmatter + raw markdown body so the
frontend can render the rail and the focused detail without a second
round-trip. The wiki directory is allowed to be absent: empty queue
is the dominant case in early operation and is reported honestly,
never faked with placeholder data.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from fastapi import APIRouter, Request

from kb.cli.wiki_review._store import _split_frontmatter, iter_pages

router = APIRouter(tags=["queue"])

PENDING = "pending_for_approve"


def _read_body(path: Path) -> str:
    text = path.read_text()
    parts = _split_frontmatter(text)
    if parts is None:
        return text
    return parts[1].lstrip("\n")


def _serialize_page(wiki_dir: Path, page) -> dict:
    return {
        "stem": page.stem,
        "rel_path": str(page.rel),
        "abs_path": str(page.path),
        "frontmatter": page.fm,
        "body": _read_body(page.path),
    }


def _tracked_wiki_files(data_dir: Path) -> set[str] | None:
    """git-tracked paths under wiki/, relative to data_dir.

    Returns ``None`` when ``data_dir`` is not a git repo — the queue then
    falls back to unfiltered listing so the surface stays honest about
    what's on disk rather than hiding it.
    """
    try:
        result = subprocess.run(
            ["git", "ls-files", "-z", "--", "wiki/"],
            cwd=data_dir,
            check=True,
            capture_output=True,
            text=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    return {p for p in result.stdout.split("\x00") if p}


@router.get("/queue")
def get_queue(request: Request) -> dict:
    cfg = request.app.state.config
    wiki_dir: Path = cfg.wiki_dir

    if not wiki_dir.is_dir():
        return {
            "pages": [],
            "meta": {
                "data_dir": str(cfg.data_dir),
                "wiki_dir": str(wiki_dir),
                "wiki_exists": False,
                "count": 0,
                "git_indexed": False,
            },
        }

    # Reject uses `git mv`, so untracked files can never leave wiki/ via
    # the API. Filter them out here so the queue and reject stay in sync;
    # otherwise an untracked copy shows up only to fail on submit.
    tracked = _tracked_wiki_files(cfg.data_dir)

    pending = [
        _serialize_page(wiki_dir, p)
        for p in iter_pages(wiki_dir)
        if p.fm.get("review_status") == PENDING
        and (tracked is None or str(p.path.relative_to(cfg.data_dir)) in tracked)
    ]
    return {
        "pages": pending,
        "meta": {
            "data_dir": str(cfg.data_dir),
            "wiki_dir": str(wiki_dir),
            "wiki_exists": True,
            "count": len(pending),
            "git_indexed": tracked is not None,
        },
    }
