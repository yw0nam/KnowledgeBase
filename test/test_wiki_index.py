"""Tests for kb_mcp.cli.wiki.index — global INDEX.md generator."""

from __future__ import annotations

from pathlib import Path

from kb_mcp.cli.wiki.index import build_index

FM = """\
---
type: entity
created: "2026-05-01"
updated: "2026-05-10"
sources: []
aliases: []
tags: []
---
"""


def _write_page(path: Path, body: str = "stub body", fm: str = FM) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(fm + "\n" + body)


def _make_wiki(tmp_path: Path) -> Path:
    wiki = tmp_path / "wiki"
    for sub in (
        "entities",
        "concepts",
        "decisions",
        "questions",
        "improvements",
        "checklists",
        "summaries",
    ):
        (wiki / sub).mkdir(parents=True, exist_ok=True)
    return wiki


def test_build_index_empty_wiki_returns_skeleton(tmp_path):
    wiki = _make_wiki(tmp_path)
    out = build_index(wiki)
    assert out.startswith("---\ntype: index\n")
    for title in (
        "Entities",
        "Concepts",
        "Decisions",
        "Questions",
        "Improvements",
        "Checklists",
        "Summaries",
    ):
        assert f"## {title}" in out
        # Empty sections show "(none)"
    assert out.count("(none)") == 7


def test_build_index_is_idempotent(tmp_path):
    wiki = _make_wiki(tmp_path)
    _write_page(wiki / "concepts" / "Alpha.md")
    _write_page(wiki / "decisions" / "2026-05-10-foo.md")

    first = build_index(wiki)
    second = build_index(wiki)
    assert first == second


def test_build_index_lists_pages_by_category(tmp_path):
    wiki = _make_wiki(tmp_path)
    _write_page(wiki / "concepts" / "Alpha.md")
    _write_page(wiki / "entities" / "kb-daily-reports" / "SomePage.md")
    _write_page(wiki / "summaries" / "daily" / "2026-05-18_agent_usage.md")

    out = build_index(wiki)

    # Concept listed under ## Concepts
    concepts_block = out.split("## Concepts")[1].split("## Decisions")[0]
    assert "[[Alpha]]" in concepts_block

    # Entities grouped by subject sub-heading
    entities_block = out.split("## Entities")[1].split("## Concepts")[0]
    assert "### kb-daily-reports" in entities_block
    assert "[[SomePage]]" in entities_block

    # Summaries grouped by bucket (daily, weekly, …)
    summaries_block = out.split("## Summaries")[1]
    assert "### daily" in summaries_block
    assert "[[2026-05-18_agent_usage]]" in summaries_block


def test_build_index_skips_underscore_index(tmp_path):
    """Per-subject ``_index.md`` hubs are NOT listed in the global TOC."""
    wiki = _make_wiki(tmp_path)
    _write_page(wiki / "concepts" / "Alpha.md")
    _write_page(
        wiki / "entities" / "kb-daily-reports" / "_index.md",
        fm="---\ntype: index\ncreated: 2026-05-01\nupdated: 2026-05-01\n---\n",
    )

    out = build_index(wiki)
    assert "[[_index]]" not in out
    assert "[[Alpha]]" in out


def test_build_index_sorts_newest_first(tmp_path):
    wiki = _make_wiki(tmp_path)
    fm_old = FM.replace("2026-05-10", "2026-05-01")
    fm_new = FM.replace("2026-05-10", "2026-05-20")
    _write_page(wiki / "concepts" / "OldPage.md", fm=fm_old)
    _write_page(wiki / "concepts" / "NewPage.md", fm=fm_new)

    out = build_index(wiki)
    concepts_block = out.split("## Concepts")[1].split("## Decisions")[0]
    new_pos = concepts_block.find("[[NewPage]]")
    old_pos = concepts_block.find("[[OldPage]]")
    assert new_pos != -1 and old_pos != -1
    assert new_pos < old_pos, "newer page should come first"


def test_build_index_dates_derived_from_pages(tmp_path):
    """Frontmatter dates derive deterministically from the page set.

    ``updated`` reflects the most recent page activity; ``created`` is the
    earliest page activity. Both use the same selection rule (prefer
    ``updated`` → fall back to ``created``) so re-runs are stable.
    """
    wiki = _make_wiki(tmp_path)
    fm_a = FM.replace('created: "2026-05-01"', 'created: "2026-03-15"').replace(
        'updated: "2026-05-10"', 'updated: "2026-04-01"'
    )
    fm_b = FM.replace('created: "2026-05-01"', 'created: "2026-06-01"').replace(
        'updated: "2026-05-10"', 'updated: "2026-06-20"'
    )
    _write_page(wiki / "concepts" / "EarlyPage.md", fm=fm_a)
    _write_page(wiki / "concepts" / "LatePage.md", fm=fm_b)

    out = build_index(wiki)
    head = out.split("---", 2)[1]
    # Earliest derived page date = EarlyPage.updated (2026-04-01).
    assert "created: 2026-04-01" in head
    # Latest derived page date = LatePage.updated (2026-06-20).
    assert "updated: 2026-06-20" in head


def test_build_index_excludes_non_approved(tmp_path):
    """build_index should skip pages with review_status != approved."""
    from kb_mcp.cli.wiki.index import build_index

    wiki = tmp_path / "wiki"
    (wiki / "entities" / "Subj").mkdir(parents=True)
    (wiki / "concepts").mkdir(parents=True)

    approved = """\
---
type: entity
review_status: approved
created: "2026-05-19"
updated: "2026-05-19"
sources: []
tags: []
---

# Approved
"""
    pending = """\
---
type: concept
review_status: pending_for_approve
created: "2026-05-19"
updated: "2026-05-19"
sources: []
tags: []
---

# Pending
"""
    not_processed = """\
---
type: concept
review_status: not_processed
created: "2026-05-19"
updated: "2026-05-19"
sources: []
tags: []
---

# NotProcessed
"""
    (wiki / "entities" / "Subj" / "Approved.md").write_text(approved)
    (wiki / "concepts" / "Pending.md").write_text(pending)
    (wiki / "concepts" / "NotProcessed.md").write_text(not_processed)

    content = build_index(wiki)
    assert "[[Approved]]" in content
    assert "[[Pending]]" not in content
    assert "[[NotProcessed]]" not in content


def test_build_index_includes_pages_without_review_status(tmp_path):
    """Pages of types outside REVIEW_STATUS_TYPES (e.g. summary) appear regardless."""
    from kb_mcp.cli.wiki.index import build_index

    wiki = tmp_path / "wiki"
    (wiki / "summaries" / "2026" / "05").mkdir(parents=True)
    summary = """\
---
type: summary
created: "2026-05-19"
updated: "2026-05-19"
sources: []
tags: []
---

# Daily memory
"""
    (wiki / "summaries" / "2026" / "05" / "2026-05-19-memory.md").write_text(summary)
    content = build_index(wiki)
    assert "[[2026-05-19-memory]]" in content
