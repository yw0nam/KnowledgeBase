"""Pure aggregation helpers for the /api/dashboard route.

Split out of ``dashboard.py`` to keep that module under the 600-line
hard cap (see ``src/CLAUDE.md``). Everything in here is pure
computation: file walking, frontmatter parsing, date helpers, and the
per-section builders. The route module owns request handling and the
final response assembly.

These helpers are package-private (leading underscore) and not part of
any public API. The dashboard route is the only intended caller.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

import yaml

from kb.cli.wiki_review._store import _split_frontmatter

KST = ZoneInfo("Asia/Seoul")

CANONICAL_TYPES: tuple[str, ...] = (
    "entity",
    "concept",
    "decision",
    "improvement",
    "checklist",
    "question",
    "summary",
)

KNOWN_SOURCE_KINDS: tuple[str, ...] = (
    "github",
    "conversations",
    "calendar",
    "web",
    "manual",
)

LOG_TAIL_BYTES = 4096
STALE_THRESHOLD_HOURS = 24
EXPIRING_WINDOW_HOURS = 72
RECENT_REJECTIONS_LIMIT = 5
FEEDBACK_EXCERPT_MAX = 140
# Mirrors the ttl-sweep --days default; see docs/workflows/wiki-approval-workflow.md.
AUTO_REJECT_TTL_DAYS = 7


@dataclass
class _PageRecord:
    """One parsed page from wiki/ or rejected/."""

    rel_path: str
    stem: str
    fm: dict
    body: str
    inferred_type: str  # frontmatter ``type`` or "summary" when inferred from path


# ---------------------------------------------------------------------------
# File walking + parsing
# ---------------------------------------------------------------------------


def _load_records(root: Path, under_summaries_is_summary: bool) -> list[_PageRecord]:
    """Walk ``root`` and parse every ``*.md`` with frontmatter.

    Malformed files are silently skipped (returning a 500 for one bad
    file would defeat the purpose of an operator dashboard). When
    ``under_summaries_is_summary`` is True, any page whose relative
    path starts with ``summaries/`` and which lacks an explicit
    ``type`` is treated as a summary — wiki summary pages don't all
    carry ``type: summary`` in their frontmatter.
    """
    out: list[_PageRecord] = []
    if not root.is_dir():
        return out
    for path in sorted(root.rglob("*.md")):
        if path.name in ("_index.md", "INDEX.md"):
            continue
        try:
            text = path.read_text()
        except OSError:
            continue
        parts = _split_frontmatter(text)
        if parts is None:
            continue
        try:
            fm = yaml.safe_load(parts[0]) or {}
        except yaml.YAMLError:
            continue
        if not isinstance(fm, dict):
            continue
        body = parts[1].lstrip("\n")
        rel = path.relative_to(root).as_posix()
        inferred = str(fm.get("type") or "").strip()
        if not inferred and under_summaries_is_summary and rel.startswith("summaries/"):
            inferred = "summary"
        out.append(
            _PageRecord(
                rel_path=rel,
                stem=path.stem,
                fm=fm,
                body=body,
                inferred_type=inferred,
            )
        )
    return out


# ---------------------------------------------------------------------------
# Date helpers
# ---------------------------------------------------------------------------


def _parse_ts(value) -> datetime.datetime | None:
    """Parse an ISO timestamp into a KST-aware datetime, or None.

    Accepts both date-only (``YYYY-MM-DD``) and full ISO timestamps,
    with or without timezone. Naive timestamps are assumed KST.
    """
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    # date-only short form
    try:
        if len(s) == 10 and s[4] == "-" and s[7] == "-":
            d = datetime.date.fromisoformat(s)
            return datetime.datetime(d.year, d.month, d.day, tzinfo=KST)
    except ValueError:
        pass
    # full ISO
    try:
        dt = datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=KST)
    return dt.astimezone(KST)


def _monday_of(d: datetime.date) -> datetime.date:
    """Return the Monday (ISO week start) of the week containing ``d``."""
    return d - datetime.timedelta(days=d.isoweekday() - 1)


def _resolve_window(
    weeks: int, today: datetime.date
) -> tuple[datetime.date, datetime.date]:
    """Inclusive [from, to] covering the last ``weeks`` weeks ending today."""
    return (today - datetime.timedelta(days=weeks * 7 - 1), today)


# ---------------------------------------------------------------------------
# Source-kind classification
# ---------------------------------------------------------------------------


def _source_kinds(fm_sources) -> set[str]:
    """Distinct source kinds touched by a page.

    A kind is the first path segment after ``raw/``. Sources that
    don't start with ``raw/`` — or pages with no sources at all —
    contribute ``unknown``. Returns at least ``{"unknown"}`` for
    empty input so the caller can attribute every page to something.
    """
    if not isinstance(fm_sources, list) or not fm_sources:
        return {"unknown"}
    kinds: set[str] = set()
    for src in fm_sources:
        if not isinstance(src, str):
            kinds.add("unknown")
            continue
        parts = src.strip().split("/")
        if len(parts) >= 2 and parts[0] == "raw" and parts[1] in KNOWN_SOURCE_KINDS:
            kinds.add(parts[1])
        else:
            kinds.add("unknown")
    return kinds


# ---------------------------------------------------------------------------
# Aggregators
# ---------------------------------------------------------------------------


@dataclass
class _Event:
    """One countable event in the window."""

    type: str
    kind: Literal["approved", "rejected_user", "rejected_auto_ttl"]
    when: datetime.datetime
    source_kinds: set[str]


def _collect_events(
    approved_pages: list[_PageRecord],
    rejected_pages: list[_PageRecord],
    window_from: datetime.date,
    window_to: datetime.date,
) -> list[_Event]:
    """Reduce parsed pages to in-window timestamped events.

    Pages missing the relevant timestamp are skipped per spec —
    invisible to the dashboard is the honest default.
    """
    events: list[_Event] = []
    for page in approved_pages:
        if page.fm.get("review_status") != "approved":
            continue
        if not page.inferred_type:
            continue
        ts = _parse_ts(page.fm.get("approved_at"))
        if ts is None:
            continue
        d = ts.date()
        if d < window_from or d > window_to:
            continue
        events.append(
            _Event(
                type=page.inferred_type,
                kind="approved",
                when=ts,
                source_kinds=_source_kinds(page.fm.get("sources")),
            )
        )
    for page in rejected_pages:
        rejected_by = page.fm.get("rejected_by")
        if rejected_by not in ("user", "auto_ttl"):
            continue
        if not page.inferred_type:
            continue
        ts = _parse_ts(page.fm.get("rejected_at"))
        if ts is None:
            continue
        d = ts.date()
        if d < window_from or d > window_to:
            continue
        events.append(
            _Event(
                type=page.inferred_type,
                kind="rejected_user" if rejected_by == "user" else "rejected_auto_ttl",
                when=ts,
                source_kinds=_source_kinds(page.fm.get("sources")),
            )
        )
    return events


def _build_activity(
    events: list[_Event], window_from: datetime.date, window_to: datetime.date
) -> list[dict]:
    """One row per ISO week (Monday) in chronological order."""
    first_monday = _monday_of(window_from)
    last_monday = _monday_of(window_to)
    weeks: list[datetime.date] = []
    cur = first_monday
    while cur <= last_monday:
        weeks.append(cur)
        cur = cur + datetime.timedelta(days=7)
    buckets: dict[datetime.date, dict[str, int]] = {
        w: {"approved": 0, "rejected_user": 0, "rejected_auto_ttl": 0} for w in weeks
    }
    for ev in events:
        wk = _monday_of(ev.when.date())
        bucket = buckets.get(wk)
        if bucket is None:
            continue
        bucket[ev.kind] += 1
    return [
        {
            "week_start": w.isoformat(),
            "approved": buckets[w]["approved"],
            "rejected_user": buckets[w]["rejected_user"],
            "rejected_auto_ttl": buckets[w]["rejected_auto_ttl"],
        }
        for w in weeks
    ]


def _rate(rejected: int, total: int) -> float:
    if total <= 0:
        return 0.0
    # Round to 3 decimals so the wire shape stays compact; downstream
    # can format further if needed.
    return round(rejected / total, 3)


def _build_rejection_by_type(events: list[_Event]) -> list[dict]:
    """One row per canonical type, sorted rate desc then total desc."""
    counts: dict[str, dict[str, int]] = {
        t: {"approved": 0, "rejected": 0} for t in CANONICAL_TYPES
    }
    for ev in events:
        if ev.type not in counts:
            continue
        if ev.kind == "approved":
            counts[ev.type]["approved"] += 1
        else:
            counts[ev.type]["rejected"] += 1
    rows = []
    for t in CANONICAL_TYPES:
        approved = counts[t]["approved"]
        rejected = counts[t]["rejected"]
        total = approved + rejected
        rows.append(
            {
                "type": t,
                "rejected": rejected,
                "total": total,
                "rate": _rate(rejected, total),
            }
        )
    rows.sort(key=lambda r: (-r["rate"], -r["total"]))
    return rows


def _build_rejection_by_source_kind(events: list[_Event]) -> list[dict]:
    """One row per known source kind plus ``unknown``.

    A page that touches multiple kinds is counted once per distinct
    kind (per spec). ``unknown`` is always last regardless of rate so
    the operator's eye lands on the actionable kinds first.
    """
    all_kinds: tuple[str, ...] = KNOWN_SOURCE_KINDS + ("unknown",)
    counts: dict[str, dict[str, int]] = {
        k: {"approved": 0, "rejected": 0} for k in all_kinds
    }
    for ev in events:
        for k in ev.source_kinds:
            bucket = counts.get(k)
            if bucket is None:
                # Defensive: _source_kinds only emits known + "unknown".
                bucket = counts["unknown"]
            if ev.kind == "approved":
                bucket["approved"] += 1
            else:
                bucket["rejected"] += 1
    rows = []
    for k in all_kinds:
        approved = counts[k]["approved"]
        rejected = counts[k]["rejected"]
        total = approved + rejected
        rows.append(
            {
                "kind": k,
                "rejected": rejected,
                "total": total,
                "rate": _rate(rejected, total),
            }
        )
    known_rows = [r for r in rows if r["kind"] != "unknown"]
    known_rows.sort(key=lambda r: (-r["rate"], -r["total"]))
    unknown_row = next(r for r in rows if r["kind"] == "unknown")
    return known_rows + [unknown_row]


def _build_rejection_by_type_and_source(events: list[_Event]) -> dict:
    """Type × source-kind rejection matrix as a flat sparse cell list.

    Surfaces PRODUCT.md's key correlation pattern (e.g. "concept pages
    from conversations are getting rejected"). ``types`` and
    ``source_kinds`` are emitted in full (canonical order) so the
    frontend can render a fixed grid; ``cells`` is sparse — only cells
    with ``total > 0`` are emitted. Cell ordering is by type index then
    source-kind index for stable, predictable rendering.

    A page that touches multiple source kinds contributes once to each
    cell, mirroring ``_build_rejection_by_source_kind``.
    """
    all_kinds: tuple[str, ...] = KNOWN_SOURCE_KINDS + ("unknown",)
    type_index = {t: i for i, t in enumerate(CANONICAL_TYPES)}
    kind_index = {k: i for i, k in enumerate(all_kinds)}
    counts: dict[tuple[str, str], dict[str, int]] = {}
    for ev in events:
        if ev.type not in type_index:
            continue
        for k in ev.source_kinds:
            key_kind = k if k in kind_index else "unknown"
            cell = counts.setdefault(
                (ev.type, key_kind), {"approved": 0, "rejected": 0}
            )
            if ev.kind == "approved":
                cell["approved"] += 1
            else:
                cell["rejected"] += 1
    cells: list[dict] = []
    for (t, k), bucket in counts.items():
        approved = bucket["approved"]
        rejected = bucket["rejected"]
        total = approved + rejected
        if total <= 0:
            continue
        cells.append(
            {
                "type": t,
                "source_kind": k,
                "approved": approved,
                "rejected": rejected,
                "total": total,
                "rate": _rate(rejected, total),
            }
        )
    cells.sort(key=lambda c: (type_index[c["type"]], kind_index[c["source_kind"]]))
    return {
        "types": list(CANONICAL_TYPES),
        "source_kinds": list(all_kinds),
        "cells": cells,
    }


# ---------------------------------------------------------------------------
# Recent + expiring helpers
# ---------------------------------------------------------------------------


def _feedback_excerpt(body: str) -> str:
    """First non-empty line under ``## User Feedback``, trimmed to 140 chars.

    The User Feedback section is a CLI-reserved heading carrying the
    reviewer's reject reason — the most useful single piece of
    pattern-finding evidence on a rejected page.
    """
    if not body:
        return ""
    lines = body.splitlines()
    for i, line in enumerate(lines):
        if line.strip().lower() == "## user feedback":
            for follow in lines[i + 1 :]:
                stripped = follow.strip()
                if not stripped:
                    continue
                if stripped.startswith("#"):
                    # Next heading reached without content.
                    return ""
                if len(stripped) > FEEDBACK_EXCERPT_MAX:
                    return stripped[: FEEDBACK_EXCERPT_MAX - 1].rstrip() + "…"
                return stripped
            return ""
    return ""


def _build_recent_rejections(rejected_pages: list[_PageRecord]) -> list[dict]:
    """Top 5 rejected pages by ``rejected_at`` descending, window-agnostic."""
    enriched: list[tuple[datetime.datetime, _PageRecord]] = []
    for page in rejected_pages:
        ts = _parse_ts(page.fm.get("rejected_at"))
        if ts is None:
            continue
        enriched.append((ts, page))
    enriched.sort(key=lambda pair: pair[0], reverse=True)
    out = []
    for ts, page in enriched[:RECENT_REJECTIONS_LIMIT]:
        source_kinds = sorted(_source_kinds(page.fm.get("sources")))
        rejected_by = page.fm.get("rejected_by")
        out.append(
            {
                "stem": page.stem,
                "title": str(page.fm.get("title") or page.stem),
                "type": page.inferred_type,
                "source_kinds": source_kinds,
                "rejected_at": ts.isoformat(timespec="seconds"),
                "rejected_by": (
                    rejected_by if rejected_by in ("user", "auto_ttl") else ""
                ),
                "feedback_excerpt": _feedback_excerpt(page.body),
            }
        )
    return out


def _build_auto_reject_soon(
    wiki_pages: list[_PageRecord], now: datetime.datetime
) -> list[dict]:
    """not_processed pages within 72h of ttl-sweep auto-rejection.

    A page's ``created`` date plus ``AUTO_REJECT_TTL_DAYS`` is the moment
    ``kb-wiki-review ttl-sweep --days 7`` will sweep it. We surface
    entries whose remaining window is in ``(0h, 72h]`` so the operator
    has a chance to promote or reject manually first. Past-due entries
    are skipped — the next ttl-sweep run will catch them.
    """
    out: list[dict] = []
    for page in wiki_pages:
        if page.fm.get("review_status") != "not_processed":
            continue
        if not page.inferred_type:
            continue
        created_dt = _parse_ts(page.fm.get("created"))
        if created_dt is None:
            continue
        auto_reject_at = created_dt + datetime.timedelta(days=AUTO_REJECT_TTL_DAYS)
        hours_remaining = (auto_reject_at - now).total_seconds() / 3600.0
        if hours_remaining <= 0 or hours_remaining > EXPIRING_WINDOW_HOURS:
            continue
        out.append(
            {
                "stem": page.stem,
                "rel_path": f"wiki/{page.rel_path}",
                "type": page.inferred_type,
                "title": str(page.fm.get("title") or page.stem),
                "created_at": created_dt.date().isoformat(),
                "auto_reject_at": auto_reject_at.isoformat(timespec="seconds"),
                "hours_remaining": int(hours_remaining),
            }
        )
    out.sort(key=lambda r: r["hours_remaining"])
    return out


# ---------------------------------------------------------------------------
# Log freshness
# ---------------------------------------------------------------------------


def _log_last_entry(log_path: Path) -> str | None:
    """Most recent ``## YYYY-MM-DD`` heading in ``data/log.md``, ISO KST.

    Only the last ~4KB of the file is read — log.md grows append-only
    so the tail always carries the latest heading.
    """
    if not log_path.is_file():
        return None
    try:
        size = log_path.stat().st_size
        with log_path.open("rb") as fh:
            if size > LOG_TAIL_BYTES:
                fh.seek(-LOG_TAIL_BYTES, 2)
            tail = fh.read().decode("utf-8", errors="replace")
    except OSError:
        return None
    latest: datetime.date | None = None
    for raw in tail.splitlines():
        line = raw.strip()
        if not line.startswith("## "):
            continue
        # Heading like "## 2026-05-18" or "## 2026-05-18 (note)".
        rest = line[3:].strip()
        token = rest.split()[0] if rest else ""
        if len(token) < 10:
            continue
        try:
            d = datetime.date.fromisoformat(token[:10])
        except ValueError:
            continue
        if latest is None or d > latest:
            latest = d
    if latest is None:
        return None
    # Anchor heading-only dates to midnight KST. The contract asks for
    # an ISO timestamp, and the log doesn't reliably carry time-of-day.
    return datetime.datetime(
        latest.year, latest.month, latest.day, tzinfo=KST
    ).isoformat(timespec="seconds")


def _is_stale(log_last_entry: str | None, now: datetime.datetime) -> bool:
    if log_last_entry is None:
        return False
    try:
        last = datetime.datetime.fromisoformat(log_last_entry)
    except ValueError:
        return False
    if last.tzinfo is None:
        last = last.replace(tzinfo=KST)
    return (now - last).total_seconds() > STALE_THRESHOLD_HOURS * 3600
