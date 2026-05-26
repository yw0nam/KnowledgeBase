"""Decision-browser read endpoints (Phase 2 §6.4).

- ``GET /api/decisions`` — filterable, paginated listing built from a
  fresh markdown scan (no index; corpus is ~300 pages, sub-second on
  SSD). Joins ``last_edited_at`` from ``wiki_edits`` and
  ``dispatch_summary`` from ``dispatches`` per stem with one grouped
  query each.
- ``GET /api/enums/categories`` — distinct ``category`` values
  currently in use (open string, not enforced). Sorted, deduped,
  empty until a page actually sets a category.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import yaml
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from kb.cli.wiki_review._store import _split_frontmatter
from kb.db import get_session
from kb.db.models import Dispatch, WikiEdit

router = APIRouter(tags=["decisions"])


def _read_fm(path: Path) -> dict | None:
    """Parse the frontmatter block from a wiki page; ``None`` on failure."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    parts = _split_frontmatter(text)
    if parts is None:
        return None
    try:
        fm = yaml.safe_load(parts[0]) or {}
    except yaml.YAMLError:
        return None
    return fm if isinstance(fm, dict) else None


def _scan_dir(root: Path, *, data_dir: Path) -> list[dict]:
    """Walk ``root/*.md`` and return one summary row per page.

    Stems are derived from the file name; the relative ``path`` is
    expressed against ``data_dir`` so the response is portable across
    machines with different absolute roots.
    """
    out: list[dict] = []
    if not root.exists():
        return out
    for f in sorted(root.rglob("*.md")):
        if f.name in ("_index.md", "INDEX.md"):
            continue
        fm = _read_fm(f)
        if fm is None:
            continue
        out.append(
            {
                "stem": f.stem,
                "path": str(f.relative_to(data_dir)),
                "type": fm.get("type"),
                "category": fm.get("category"),
                "tags": fm.get("tags", []) or [],
                "review_status": fm.get("review_status"),
                "sources": fm.get("sources", []) or [],
                "captured_at": fm.get("captured_at") or fm.get("created"),
            }
        )
    return out


def _last_edited_map(session: Session, stems: Iterable[str]) -> dict[str, str]:
    stems_list = list(stems)
    if not stems_list:
        return {}
    rows = session.execute(
        select(WikiEdit.page_stem, func.max(WikiEdit.edited_at))
        .where(WikiEdit.page_stem.in_(stems_list))
        .group_by(WikiEdit.page_stem)
    ).all()
    return {stem: edited for stem, edited in rows}


def _dispatch_summary_map(session: Session, stems: Iterable[str]) -> dict[str, dict]:
    """One ``{count, last_status}`` per stem with any dispatches.

    Spec §6.4: "latest by ``dispatches.last_status_at DESC``, ties
    broken by ``dispatched_at DESC``". Literal columns (no COALESCE):
    SQLite puts NULL last on ``DESC`` by default, so a row with NULL
    ``last_status_at`` loses to any row with a real timestamp
    regardless of ``dispatched_at``. Computed in two queries — a
    per-stem COUNT and a per-stem-latest row fetched in Python —
    because SQLite's ``ROW_NUMBER`` support is flaky across
    Alembic-managed versions and the corpus is tiny.
    """
    stems_list = list(stems)
    if not stems_list:
        return {}

    counts = dict(
        session.execute(
            select(Dispatch.page_stem, func.count(Dispatch.id))
            .where(Dispatch.page_stem.in_(stems_list))
            .group_by(Dispatch.page_stem)
        ).all()
    )
    if not counts:
        return {}

    rows = (
        session.execute(
            select(Dispatch)
            .where(Dispatch.page_stem.in_(stems_list))
            .order_by(
                desc(Dispatch.last_status_at),
                desc(Dispatch.dispatched_at),
                desc(Dispatch.id),
            )
        )
        .scalars()
        .all()
    )

    latest_by_stem: dict[str, Dispatch] = {}
    for r in rows:
        latest_by_stem.setdefault(r.page_stem, r)

    return {
        stem: {"count": counts.get(stem, 0), "last_status": latest_by_stem[stem].status}
        for stem in latest_by_stem
    }


def _passes(
    item: dict,
    *,
    status: list[str] | None,
    type_: list[str] | None,
    category: list[str] | None,
    source: list[str] | None,
    edited_since: str | None,
) -> bool:
    if status and item.get("review_status") not in status:
        return False
    if type_ and item.get("type") not in type_:
        return False
    if category and item.get("category") not in category:
        return False
    if source:
        sources = item.get("sources") or []
        needles = [s.lower() for s in source]
        if not any(
            isinstance(src, str) and any(n in src.lower() for n in needles)
            for src in sources
        ):
            return False
    if edited_since is not None:
        last = item.get("last_edited_at")
        if last is None or last < edited_since:
            return False
    return True


# ---------------------------------------------------------------------------
# GET /api/decisions
# ---------------------------------------------------------------------------


@router.get("/decisions")
def list_decisions(
    request: Request,
    status: list[str] | None = Query(default=None),
    type: list[str] | None = Query(default=None),
    category: list[str] | None = Query(default=None),
    source: list[str] | None = Query(default=None),
    edited_since: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=200),
    session: Session = Depends(get_session),
) -> dict:
    cfg = request.app.state.config
    data_dir: Path = cfg.data_dir
    wiki_dir: Path = cfg.wiki_dir

    items = _scan_dir(wiki_dir, data_dir=data_dir)

    # Rejected pages live under data/rejected/ (git-mv'd out by the
    # reject flow). Only pull them in when the filter asks for them.
    if status is not None and "rejected" in status:
        rejected_dir = data_dir / "rejected"
        rejected_items = _scan_dir(rejected_dir, data_dir=data_dir)
        for it in rejected_items:
            it["review_status"] = "rejected"
        items.extend(rejected_items)

    stems = [it["stem"] for it in items]
    last_edited = _last_edited_map(session, stems)
    dispatch_summary = _dispatch_summary_map(session, stems)

    for it in items:
        it["last_edited_at"] = last_edited.get(it["stem"]) or it.get("captured_at")
        it["dispatch_summary"] = dispatch_summary.get(it["stem"])

    filtered = [
        it
        for it in items
        if _passes(
            it,
            status=status,
            type_=type,
            category=category,
            source=source,
            edited_since=edited_since,
        )
    ]

    filtered.sort(key=lambda it: it.get("last_edited_at") or "", reverse=True)

    total = len(filtered)
    start = (page - 1) * per_page
    end = start + per_page
    return {
        "items": filtered[start:end],
        "total": total,
        "page": page,
        "per_page": per_page,
    }


# ---------------------------------------------------------------------------
# GET /api/enums/categories
# ---------------------------------------------------------------------------


@router.get("/enums/categories")
def list_categories(
    request: Request,
    type: str | None = Query(default=None),
) -> dict:
    """Distinct ``category`` values currently in use for ``type``.

    Open string — the frontend uses these as suggestions, not as an
    enum gate. Empty until pages actually start carrying categories.
    """
    cfg = request.app.state.config
    data_dir: Path = cfg.data_dir

    seen: set[str] = set()
    for root in (cfg.wiki_dir, data_dir / "rejected"):
        for it in _scan_dir(root, data_dir=data_dir):
            if type is not None and it.get("type") != type:
                continue
            cat = it.get("category")
            if isinstance(cat, str) and cat:
                seen.add(cat)
    return {"categories": sorted(seen)}
