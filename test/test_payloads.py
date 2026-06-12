"""Tests for kb.cli._payloads — pure payload parsers extracted from db_api.py."""

from __future__ import annotations

import pytest

from kb.cli._payloads import (
    PayloadError,
    _split_frontmatter,
    markdown_page_payload,
    raw_source_payload,
)

# ---------------------------------------------------------------------------
# _split_frontmatter error cases
# ---------------------------------------------------------------------------


def test_split_frontmatter_missing_opening_delimiter() -> None:
    """Markdown without leading '---\\n' raises PayloadError."""
    with pytest.raises(PayloadError, match="frontmatter"):
        _split_frontmatter("# No frontmatter here\n\nBody.\n")


def test_split_frontmatter_missing_closing_delimiter() -> None:
    """Markdown with only an opening delimiter but no closing '---' raises PayloadError."""
    with pytest.raises(PayloadError, match="closing delimiter"):
        _split_frontmatter("---\ntype: summary\nno closing delimiter\n")


# ---------------------------------------------------------------------------
# markdown_page_payload
# ---------------------------------------------------------------------------


_FULL_MD = """\
---
type: summary
subtype: daily
date: "2026-06-04"
sources: []
tags: [agent-usage]
---

# Daily Report

Body.
"""


def test_markdown_page_payload_preserves_frontmatter_and_body() -> None:
    """Ported from test_db_canonical_api.py — import now comes from _payloads."""
    payload = markdown_page_payload(
        markdown=_FULL_MD,
        export_path="wiki/summaries/2026/06/2026-06-04-usage.md",
        slug="2026-06-04-usage",
        origin="ingested",
        source="test",
    )
    assert payload["frontmatter"] == {
        "type": "summary",
        "subtype": "daily",
        "date": "2026-06-04",
        "sources": [],
        "tags": ["agent-usage"],
    }
    assert payload["body_md"].startswith("\n\n# Daily Report")
    assert payload["export_path"] == "wiki/summaries/2026/06/2026-06-04-usage.md"
    assert payload["slug"] == "2026-06-04-usage"
    assert payload["type"] == "summary"
    assert payload["origin"] == "ingested"
    assert payload["source"] == "test"


def test_markdown_page_payload_missing_type_raises() -> None:
    md = """\
---
subtype: daily
sources: []
---

# No type field
"""
    with pytest.raises(PayloadError, match="type"):
        markdown_page_payload(
            markdown=md,
            export_path="wiki/x.md",
            slug="x",
            origin="ingested",
            source="cli",
        )


# ---------------------------------------------------------------------------
# raw_source_payload
# ---------------------------------------------------------------------------


_RAW_MD = """\
---
type: web_article
source_url: https://example.com/paper
captured_at: "2026-06-04T00:00:00Z"
contributor: cli
---

# Example Paper

Abstract text here.
"""


def test_raw_source_payload_returns_expected_keys() -> None:
    payload = raw_source_payload(
        markdown=_RAW_MD,
        source_key="raw/web/huggingface/daily_papers_2026-06-04.md",
        source_type="web_article",
    )
    assert payload["source_key"] == "raw/web/huggingface/daily_papers_2026-06-04.md"
    assert payload["source_type"] == "web_article"
    assert payload["source_url"] == "https://example.com/paper"
    assert payload["captured_at"] == "2026-06-04T00:00:00Z"
    assert payload["title"] == "Example Paper"
    assert "content_md" in payload
    assert "frontmatter" in payload


def test_raw_source_payload_falls_back_to_frontmatter_type() -> None:
    md = """\
---
type: github_issue
source_url: https://github.com/org/repo/issues/1
captured_at: "2026-06-04T00:00:00Z"
contributor: cli
---

# Some Issue
"""
    payload = raw_source_payload(
        markdown=md,
        source_key="raw/github/issues/repo_1.md",
    )
    assert payload["source_type"] == "github_issue"


def test_raw_source_payload_missing_frontmatter_raises() -> None:
    with pytest.raises(PayloadError):
        raw_source_payload(
            markdown="# No frontmatter\n\nJust body.\n",
            source_key="raw/x.md",
        )
