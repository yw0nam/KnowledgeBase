"""Shared page-serialization helper.

Both ``GET /api/queue`` and ``GET /api/pages/{stem}`` return pages in
the same shape (frontmatter + body) so the frontend can reuse one
TypeScript type. Keep the producer in one place.
"""

from __future__ import annotations

from pathlib import Path

from kb.cli.wiki_review._store import Page, _split_frontmatter


def _read_body(path: Path) -> str:
    text = path.read_text()
    parts = _split_frontmatter(text)
    if parts is None:
        return text
    return parts[1].lstrip("\n")


def _serialize_page(wiki_dir: Path, page: Page) -> dict:
    return {
        "stem": page.stem,
        "rel_path": str(page.rel),
        "abs_path": str(page.path),
        "frontmatter": page.fm,
        "body": _read_body(page.path),
    }
