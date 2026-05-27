"""Single source of truth for the frontmatter <-> DB field mapping.

Both parse (md -> DB) and render (DB -> md) import from here so the
round-trip is lossless. Any top-level frontmatter key that is NOT a
typed column and NOT a join field falls into the JSON ``extra`` column.
"""

from __future__ import annotations

# Typed columns on the ``pages`` table (excludes id/stem/rel_path/extra).
TYPED_COLUMNS: tuple[str, ...] = (
    "type",
    "subtype",
    "category",
    "review_status",
    "period_start",
    "period_end",
    "created",
    "updated",
)

# Multi-valued frontmatter keys -> join table names.
JOIN_FIELDS: dict[str, str] = {
    "tags": "page_tags",
    "sources": "page_sources",
    "aliases": "page_aliases",
}

# Deterministic key order for the rendered block. Keys absent on a page
# are skipped at render time. ``extra`` keys are emitted, sorted, in the
# EXTRA_SLOT position.
EXTRA_SLOT = "__extra__"
RENDER_ORDER: tuple[str, ...] = (
    "type",
    "subtype",
    "category",
    "review_status",
    "period_start",
    "period_end",
    "tags",
    "sources",
    "aliases",
    EXTRA_SLOT,
    "created",
    "updated",
)
