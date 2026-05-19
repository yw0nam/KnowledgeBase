"""GET /api/dashboard — weekly-read dashboard for the operator.

Single-screen pattern view. The CLI surfaces "what is in the queue
right now"; this endpoint answers the harder question — "what is the
AI producing, and what is the user rejecting, week over week?"

Read-only. Walks ``data/wiki/`` and ``data/rejected/`` once each,
counts events that fall inside an N-week window ending today (KST),
and emits the contract documented in ``DESIGN.md``. Missing
directories degrade to a well-formed empty response; malformed
frontmatter on a single page is skipped, never fatal.

Aggregation helpers live in ``_aggregate.py`` (split out to keep
this module under the 600-line hard cap from ``src/CLAUDE.md``).

# Smoke trace (3-page corpus, window=8, today=2026-05-19):
#   data/wiki/concepts/foo.md      type=concept   review_status=approved  approved_at=2026-05-15
#   data/rejected/concepts/bar.md  type=concept   rejected_by=user        rejected_at=2026-05-17
#   data/rejected/entities/baz.md  type=entity    rejected_by=auto_ttl    rejected_at=2026-05-10
# Expected response sketch:
#   activity[-1]              -> {week_start: 2026-05-18, approved:0, rejected_user:0, rejected_auto_ttl:0}
#   activity[-2]              -> {week_start: 2026-05-11, approved:0, rejected_user:1, rejected_auto_ttl:0}  (bar)
#   activity[-3]              -> {week_start: 2026-05-04, approved:1, rejected_user:0, rejected_auto_ttl:1}  (foo, baz)
#   rejection_by_type[concept]-> total=2, rejected=1, rate=0.5
#   rejection_by_source_kind  -> depends on bar/baz sources
#   rejection_by_type_and_source -> sparse cells like {type:concept, source_kind:conversations, ...}
#   auto_reject_soon          -> pages with review_status=not_processed whose
#                                created date is between 4 and 7 days ago
#                                (i.e. within 72h of ttl-sweep auto-reject)
#   recent_rejections         -> [bar, baz]  ordered desc by rejected_at
"""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request

from kb_mcp.web.routes._aggregate import (
    AUTO_REJECT_TTL_DAYS,
    KST,
    _build_activity,
    _build_auto_reject_soon,
    _build_recent_rejections,
    _build_rejection_by_source_kind,
    _build_rejection_by_type,
    _build_rejection_by_type_and_source,
    _collect_events,
    _is_stale,
    _load_records,
    _log_last_entry,
    _resolve_window,
)

router = APIRouter(tags=["dashboard"])

ALLOWED_WINDOWS: frozenset[int] = frozenset({4, 8, 12, 24})


@router.get("/dashboard")
def get_dashboard(
    request: Request,
    window: Annotated[
        int, Query(description="Weeks of history. One of 4, 8, 12, 24.")
    ] = 8,
) -> dict:
    # FastAPI cannot coerce a query string into ``Literal[4, 8, 12, 24]``
    # (it parses "8" as a string and rejects it), so the membership check
    # is enforced here and surfaced as a 422 like a normal validation
    # error would be.
    if window not in ALLOWED_WINDOWS:
        raise HTTPException(
            status_code=422,
            detail=[
                {
                    "type": "value_error",
                    "loc": ["query", "window"],
                    "msg": "Input should be 4, 8, 12 or 24",
                    "input": window,
                }
            ],
        )
    cfg = request.app.state.config
    data_dir: Path = cfg.data_dir
    wiki_dir: Path = cfg.wiki_dir
    rejected_dir: Path = cfg.rejected_dir

    now = datetime.datetime.now(KST)
    today = now.date()
    window_from, window_to = _resolve_window(window, today)

    wiki_records = _load_records(wiki_dir, under_summaries_is_summary=True)
    rejected_records = _load_records(rejected_dir, under_summaries_is_summary=True)

    events = _collect_events(wiki_records, rejected_records, window_from, window_to)
    log_last_entry = _log_last_entry(data_dir / "log.md")

    return {
        "window": {
            "weeks": window,
            "from": window_from.isoformat(),
            "to": window_to.isoformat(),
        },
        "meta": {
            "data_dir": str(data_dir),
            "auto_reject_ttl_days": AUTO_REJECT_TTL_DAYS,
            "log_last_entry": log_last_entry,
            "is_stale": _is_stale(log_last_entry, now),
        },
        "activity": _build_activity(events, window_from, window_to),
        "rejection_by_type": _build_rejection_by_type(events),
        "rejection_by_source_kind": _build_rejection_by_source_kind(events),
        "rejection_by_type_and_source": _build_rejection_by_type_and_source(events),
        "auto_reject_soon": _build_auto_reject_soon(wiki_records, now),
        "recent_rejections": _build_recent_rejections(rejected_records),
    }
