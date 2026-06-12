"""Pure payload parsers for KB CLI consumers.

These functions parse Markdown (with YAML frontmatter) into structured dicts
suitable for passing to service-layer functions.  They have no I/O side effects.

Extracted from the now-removed ``kb.cli.db_api`` so that in-process consumers
can import them without pulling in an HTTP client.
"""

from __future__ import annotations

from typing import Any

import yaml


class PayloadError(ValueError):
    """Raised when a Markdown document cannot be parsed into a valid payload."""


def _split_frontmatter(markdown: str) -> tuple[dict[str, Any], str]:
    if not markdown.startswith("---\n"):
        raise PayloadError("markdown must start with YAML frontmatter")
    try:
        _, fm_text, body = markdown.split("---", 2)
    except ValueError as exc:
        raise PayloadError("markdown frontmatter closing delimiter is missing") from exc
    frontmatter = yaml.safe_load(fm_text) or {}
    if not isinstance(frontmatter, dict):
        raise PayloadError("markdown frontmatter must be a mapping")
    return frontmatter, body


def _first_heading(body: str, fallback: str) -> str:
    for line in body.splitlines():
        if line.startswith("# "):
            return line[2:].strip() or fallback
    return fallback


def markdown_page_payload(
    *,
    markdown: str,
    export_path: str,
    slug: str,
    origin: str,
    source: str,
) -> dict[str, Any]:
    """Parse a Markdown page into a dict suitable for ``service.pages.upsert_page``.

    Returns keys: slug, type, title, category, review_status, origin,
    frontmatter, body_md, export_path, source.
    """
    frontmatter, body = _split_frontmatter(markdown)
    page_type = frontmatter.get("type")
    if not isinstance(page_type, str) or not page_type:
        raise PayloadError("page frontmatter requires non-empty type")
    return {
        "slug": slug,
        "type": page_type,
        "title": frontmatter.get("title"),
        "category": frontmatter.get("category"),
        "review_status": frontmatter.get("review_status"),
        "origin": origin,
        "frontmatter": frontmatter,
        "body_md": body,
        "export_path": export_path,
        "source": source,
    }


def raw_source_payload(
    *,
    markdown: str,
    source_key: str,
    source_type: str | None = None,
) -> dict[str, Any]:
    """Parse a raw-source Markdown document into a dict for ``service.sources.create_raw_source``.

    Returns keys: source_key, source_type, source_url, title, captured_at,
    frontmatter, content_md.
    """
    frontmatter, body = _split_frontmatter(markdown)
    raw_type = source_type or frontmatter.get("type") or "raw"
    return {
        "source_key": source_key,
        "source_type": raw_type,
        "source_url": frontmatter.get("source_url"),
        "title": _first_heading(body, source_key),
        "captured_at": frontmatter.get("captured_at"),
        "frontmatter": frontmatter,
        "content_md": body,
    }
