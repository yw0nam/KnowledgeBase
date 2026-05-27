"""Frontmatter <-> ParsedPage (DB-shaped) conversion.

``parse_frontmatter`` is md -> DB; ``render_block`` is DB -> md. Both
go through ``_fields`` so they never disagree.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import yaml

from kb.cli.page._fields import (
    EXTRA_SLOT,
    JOIN_FIELDS,
    RENDER_ORDER,
    TYPED_COLUMNS,
)

MARKER = "# managed-by: kb-page"


@dataclass
class ParsedPage:
    typed: dict[str, object] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)
    extra: dict[str, object] = field(default_factory=dict)


def parse_frontmatter(fm: dict) -> ParsedPage:
    """Split a frontmatter dict into typed columns / join lists / extra."""
    typed: dict[str, object] = {}
    joins: dict[str, list[str]] = {"tags": [], "sources": [], "aliases": []}
    extra: dict[str, object] = {}
    for key, value in fm.items():
        if key in TYPED_COLUMNS:
            typed[key] = value
        elif key in JOIN_FIELDS:
            joins[key] = list(value or [])
        else:
            extra[key] = value
    return ParsedPage(
        typed=typed,
        tags=joins["tags"],
        sources=joins["sources"],
        aliases=joins["aliases"],
        extra=extra,
    )


def _dump_scalar_or_list(key: str, value: object) -> str:
    """YAML-dump a single ``key: value`` mapping, no trailing newline noise."""
    text = yaml.safe_dump({key: value}, sort_keys=False, allow_unicode=True)
    return text.rstrip("\n")


def render_block(page: ParsedPage) -> str:
    """Render the deterministic frontmatter block (no surrounding fences)."""
    lines: list[str] = [MARKER]
    join_values = {"tags": page.tags, "sources": page.sources, "aliases": page.aliases}
    for slot in RENDER_ORDER:
        if slot == EXTRA_SLOT:
            for k in sorted(page.extra):
                lines.append(_dump_scalar_or_list(k, page.extra[k]))
            continue
        if slot in JOIN_FIELDS:
            vals = join_values[slot]
            if vals:
                lines.append(_dump_scalar_or_list(slot, list(vals)))
            continue
        if slot in page.typed and page.typed[slot] is not None:
            lines.append(_dump_scalar_or_list(slot, page.typed[slot]))
    return "\n".join(lines) + "\n"
