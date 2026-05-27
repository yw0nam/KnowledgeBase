"""Shared frontmatter write core: ingest (md->DB) and render (DB->md).

The body is never owned by the DB — render replaces only the frontmatter
block and re-attaches the original body verbatim.
"""

from __future__ import annotations

import datetime
from collections.abc import Sequence
from pathlib import Path

import yaml
from sqlalchemy.orm import Session

from kb.cli.page._serialize import parse_frontmatter, render_block
from kb.cli.wiki_review._store import _split_frontmatter, resolve_stem
from kb.db.repos import page_repo


def _stringify_dates(value: object) -> object:
    """Recursively convert date/datetime objects to ISO strings.

    Frontmatter is text and the DB columns are TEXT/JSON, but yaml.safe_load
    auto-parses bare ``YYYY-MM-DD`` scalars into date objects. Normalizing to
    strings at the read boundary keeps the pipeline string-canonical so the
    ingest and render write paths agree, and keeps the JSON ``extra`` column
    serializable. (datetime is a subclass of date — check it first.)
    """
    if isinstance(value, datetime.datetime):
        return value.isoformat()
    if isinstance(value, datetime.date):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _stringify_dates(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_stringify_dates(v) for v in value]
    return value


def _read_split(path: Path) -> tuple[dict, str]:
    """Return (frontmatter dict, body) for a wiki page file."""
    text = path.read_text()
    parts = _split_frontmatter(text)
    if parts is None:
        raise ValueError(f"{path}: missing or malformed frontmatter")
    fm = yaml.safe_load(parts[0]) or {}
    if not isinstance(fm, dict):
        raise ValueError(f"{path}: frontmatter is not a mapping")
    fm = _stringify_dates(fm)
    return fm, parts[1]


def _write_with_block(path: Path, block: str, body: str) -> None:
    body = body.lstrip("\n")
    path.write_text(f"---\n{block}---\n\n{body}")


def ingest_file(session: Session, *, wiki_dir: Path, path: Path) -> None:
    """Parse ``path``, upsert into the DB, then re-render its block."""
    fm, body = _read_split(path)
    parsed = parse_frontmatter(fm)
    stem = path.stem
    rel_path = str(path.relative_to(wiki_dir))
    page_repo.upsert_page(
        session,
        stem=stem,
        rel_path=rel_path,
        typed=parsed.typed,
        tags=parsed.tags,
        sources=parsed.sources,
        aliases=parsed.aliases,
        extra=parsed.extra,
    )
    _write_with_block(path, render_block(parsed), body)


def render_page_file(session: Session, *, wiki_dir: Path, stem: str) -> None:
    """Regenerate the frontmatter block of ``stem`` from the DB row."""
    row = page_repo.get_by_stem(session, stem)
    if row is None:
        raise ValueError(f"no pages row for stem {stem!r}")
    path = resolve_stem(wiki_dir, stem)
    _, body = _read_split(path)
    # parse_frontmatter drops None typed values, so no post-filter is needed.
    # The DB already returns string dates (stringified at the read boundary),
    # so no coercion is needed here.
    raw_fm = {
        "type": row.type,
        "subtype": row.subtype,
        "category": row.category,
        "review_status": row.review_status,
        "period_start": row.period_start,
        "period_end": row.period_end,
        "created": row.created,
        "updated": row.updated,
        "tags": page_repo.get_tags(session, row.id),
        "sources": page_repo.get_sources(session, row.id),
        "aliases": page_repo.get_aliases(session, row.id),
        **(row.extra or {}),
    }
    parsed = parse_frontmatter(raw_fm)
    _write_with_block(path, render_block(parsed), body)


def apply_frontmatter_change(
    session: Session,
    *,
    stem: str,
    changes: Sequence[tuple[str, object, object]],
    source: str,
    wiki_dir: Path,
) -> None:
    """Field-change + audit + re-render. Fully wired in PR2/PR3.

    PR1 ships the signature only so later PRs import a stable name; it is
    not called by import/render and raises if invoked.
    """
    raise NotImplementedError("apply_frontmatter_change lands in PR2/PR3")
