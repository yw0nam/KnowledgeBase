"""Tests for src/kb_mcp/cli/lint_wiki.py — stub + index sync checks."""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

import pytest

import kb_mcp.cli.lint_wiki as lint_mod_module


@pytest.fixture(scope="module")
def lint_mod():
    return lint_mod_module


# ── helpers to build a tmp wiki tree ─────────────────────────────────


FM = """\
---
type: entity
created: "2026-04-27"
updated: "2026-04-27"
sources: []
aliases: []
tags: []
---
"""


def write_page(path: Path, body: str = "", fm: str = FM) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(fm + "\n" + body)
    return path


def make_wiki_root(tmp_path: Path) -> Path:
    """Create wiki/ with the standard subdir layout."""
    wiki = tmp_path / "wiki"
    for sub in ("entities", "concepts", "decisions", "summaries", "questions"):
        (wiki / sub).mkdir(parents=True, exist_ok=True)
    return wiki


# ── Stub check ──────────────────────────────────────────────────────


def test_stub_warns_on_short_body(lint_mod, tmp_path):
    wiki = make_wiki_root(tmp_path)
    # Subject hub listing the stub page — keeps index sync clean.
    write_page(
        wiki / "entities" / "Subj" / "_index.md",
        "# Subj\n\n## Pages\n\n- [[Tiny]]\n",
    )
    write_page(wiki / "entities" / "Subj" / "2026-04" / "Tiny.md", body="too short")

    result = lint_mod.LintResult()
    lint_mod.lint(result, wiki_dir=wiki)

    stub_warns = [w for w in result.warnings if "stub page" in w]
    assert len(stub_warns) == 1
    assert "Tiny.md" in stub_warns[0]
    assert f"< {lint_mod.STUB_THRESHOLD_CHARS}" in stub_warns[0]


def test_stub_no_warn_on_full_body(lint_mod, tmp_path):
    wiki = make_wiki_root(tmp_path)
    write_page(
        wiki / "entities" / "Subj" / "_index.md",
        "# Subj\n\n## Pages\n\n- [[Big]]\n",
    )
    long_body = "This page has plenty of content. " * 10  # > 100 chars
    write_page(wiki / "entities" / "Subj" / "2026-04" / "Big.md", body=long_body)

    result = lint_mod.LintResult()
    lint_mod.lint(result, wiki_dir=wiki)

    stub_warns = [w for w in result.warnings if "stub page" in w]
    assert stub_warns == []


def test_stub_excludes_index_md(lint_mod, tmp_path):
    """_index.md hubs are allowed to be short — handled by index sync, not stub."""
    wiki = make_wiki_root(tmp_path)
    long_body = "This page has plenty of content. " * 10
    write_page(wiki / "entities" / "Subj" / "2026-04" / "Big.md", body=long_body)
    # Hub itself is short and lists the page.
    write_page(
        wiki / "entities" / "Subj" / "_index.md",
        "## Pages\n\n[[Big]]",
    )

    result = lint_mod.LintResult()
    lint_mod.lint(result, wiki_dir=wiki)

    stub_warns = [w for w in result.warnings if "stub page" in w]
    assert stub_warns == []


# ── Index sync ─────────────────────────────────────────────────────


def test_index_sync_error_on_listed_but_missing(lint_mod, tmp_path):
    wiki = make_wiki_root(tmp_path)
    # Hub references PageOne but no file with that stem exists.
    write_page(
        wiki / "entities" / "Subj" / "_index.md",
        "# Subj\n\n## Pages\n\n- [[PageOne]]\n",
    )

    result = lint_mod.LintResult()
    lint_mod.lint(result, wiki_dir=wiki)

    sync_errors = [e for e in result.errors if "_index.md lists [[PageOne]]" in e]
    assert len(sync_errors) == 1


def test_index_sync_warn_on_orphan_page(lint_mod, tmp_path):
    wiki = make_wiki_root(tmp_path)
    long_body = "This page has plenty of content. " * 10
    write_page(wiki / "entities" / "Subj" / "2026-04" / "Listed.md", body=long_body)
    write_page(
        wiki / "entities" / "Subj" / "2026-04" / "NotListed.md",
        body=long_body,
    )
    # Hub lists only Listed.
    write_page(
        wiki / "entities" / "Subj" / "_index.md",
        "# Subj\n\n## Pages\n\n- [[Listed]]\n",
    )

    result = lint_mod.LintResult()
    lint_mod.lint(result, wiki_dir=wiki)

    sync_warns = [
        w for w in result.warnings if "page not listed in Subj/_index.md" in w
    ]
    assert len(sync_warns) == 1
    assert "NotListed.md" in sync_warns[0]


def test_index_sync_clean(lint_mod, tmp_path):
    """Hub matches disk exactly — no sync errors, no sync warnings."""
    wiki = make_wiki_root(tmp_path)
    long_body = "This page has plenty of content. " * 10
    write_page(wiki / "entities" / "Subj" / "2026-04" / "Alpha.md", body=long_body)
    write_page(wiki / "entities" / "Subj" / "2026-04" / "Beta.md", body=long_body)
    write_page(
        wiki / "entities" / "Subj" / "_index.md",
        "# Subj\n\n## Pages\n\n- [[Alpha]]\n- [[Beta]]\n",
    )

    result = lint_mod.LintResult()
    lint_mod.lint(result, wiki_dir=wiki)

    sync_errors = [e for e in result.errors if "_index.md lists" in e]
    sync_warns = [w for w in result.warnings if "not listed in" in w]
    assert sync_errors == []
    assert sync_warns == []


# ── Smoke: clean minimal wiki produces zero new-style ERRORs ────────


def test_clean_minimal_wiki_zero_errors(lint_mod, tmp_path):
    """A minimal but well-formed wiki triggers no errors at all."""
    wiki = make_wiki_root(tmp_path)
    long_body = (
        "This is a real page with enough content to clear the stub threshold. "
        "It mentions [[Alpha]] in passing. "
    )
    write_page(wiki / "entities" / "Subj" / "2026-04" / "Alpha.md", body=long_body)
    write_page(
        wiki / "entities" / "Subj" / "_index.md",
        "# Subj\n\n## Pages\n\n- [[Alpha]]\n",
    )

    result = lint_mod.LintResult()
    lint_mod.lint(result, wiki_dir=wiki)

    assert result.errors == [], f"unexpected errors: {result.errors}"


# ── Index sync scope: code blocks + missing Pages section ──────────


def test_index_sync_ignores_wikilinks_in_code_blocks(lint_mod, tmp_path):
    """Wikilinks inside fenced code blocks must not trigger sync errors.

    Hub has a real Pages section with [[Real]] (which exists on disk), plus a
    fenced code block in a non-Pages section containing [[FakePlaceholder]]
    (which does not exist on disk). The fake link must not surface as a
    sync ``_index.md lists [[...]]`` error.
    """
    wiki = make_wiki_root(tmp_path)
    long_body = "This page has plenty of content. " * 10
    write_page(wiki / "entities" / "Subj" / "2026-04" / "Real.md", body=long_body)
    hub_body = (
        "# Subj\n\n"
        "## Pages\n\n"
        "- [[Real]]\n\n"
        "## Notes\n\n"
        "Example template (do not parse):\n\n"
        "```\n"
        "[[FakePlaceholder|Page Title]]\n"
        "```\n"
    )
    write_page(wiki / "entities" / "Subj" / "_index.md", hub_body)

    result = lint_mod.LintResult()
    lint_mod.lint(result, wiki_dir=wiki)

    sync_errors = [
        e for e in result.errors if "_index.md lists [[FakePlaceholder]]" in e
    ]
    assert sync_errors == [], f"FakePlaceholder leaked into sync check: {sync_errors}"


# ── Placeholder regex matches `<!-- LLM TODO: -->` markers ─────────


def test_placeholder_warn_on_llm_todo(lint_mod, tmp_path):
    """Wiki templates emit `<!-- LLM TODO: ... -->` — lint must detect it."""
    wiki = make_wiki_root(tmp_path)
    body = (
        "# Title\n\n"
        "## Overview\n\n"
        "<!-- LLM TODO: 1-2 paragraph summary -->\n\n"
        "## Key Details\n\n"
        "<!-- LLM TODO: technical details -->\n"
    )
    write_page(wiki / "entities" / "Subj" / "2026-04" / "Page.md", body=body)
    write_page(
        wiki / "entities" / "Subj" / "_index.md",
        "# Subj\n\n## Pages\n\n- [[Page]]\n",
    )

    result = lint_mod.LintResult()
    lint_mod.lint(result, wiki_dir=wiki)

    placeholder_warns = [w for w in result.warnings if "unfilled" in w]
    assert len(placeholder_warns) == 1
    assert "Page.md" in placeholder_warns[0]
    assert "2 unfilled" in placeholder_warns[0]


def test_placeholder_warn_on_legacy_llm_colon(lint_mod, tmp_path):
    """Legacy `<!-- LLM: ... -->` form must still be detected."""
    wiki = make_wiki_root(tmp_path)
    long_body = "This page has plenty of content. " * 5
    body = long_body + "\n<!-- LLM: legacy -->\n"
    write_page(wiki / "entities" / "Subj" / "2026-04" / "Legacy.md", body=body)
    write_page(
        wiki / "entities" / "Subj" / "_index.md",
        "# Subj\n\n## Pages\n\n- [[Legacy]]\n",
    )

    result = lint_mod.LintResult()
    lint_mod.lint(result, wiki_dir=wiki)

    placeholder_warns = [w for w in result.warnings if "unfilled" in w]
    assert len(placeholder_warns) == 1


# ── Frontmatter type field (Fix 2) ──────────────────────────────────


def test_missing_type_field_errors(lint_mod, tmp_path):
    """A page without `type:` must error — previously silently skipped."""
    wiki = make_wiki_root(tmp_path)
    fm_no_type = (
        "---\n"
        'created: "2026-04-27"\n'
        'updated: "2026-04-27"\n'
        "sources: []\n"
        "tags: []\n"
        "---\n"
    )
    long_body = "This page has plenty of content. " * 5
    write_page(
        wiki / "entities" / "Subj" / "2026-04" / "NoType.md",
        body=long_body,
        fm=fm_no_type,
    )
    write_page(
        wiki / "entities" / "Subj" / "_index.md",
        "# Subj\n\n## Pages\n\n- [[NoType]]\n",
    )

    result = lint_mod.LintResult()
    lint_mod.lint(result, wiki_dir=wiki)

    type_errors = [
        e
        for e in result.errors
        if "missing frontmatter field: type" in e and "NoType.md" in e
    ]
    assert len(type_errors) == 1


def test_unknown_type_warns(lint_mod, tmp_path):
    wiki = make_wiki_root(tmp_path)
    fm_unknown = (
        "---\n"
        "type: weirdtype\n"
        'created: "2026-04-27"\n'
        'updated: "2026-04-27"\n'
        "sources: []\n"
        "tags: []\n"
        "---\n"
    )
    long_body = "This page has plenty of content. " * 5
    write_page(
        wiki / "entities" / "Subj" / "2026-04" / "Weird.md",
        body=long_body,
        fm=fm_unknown,
    )
    write_page(
        wiki / "entities" / "Subj" / "_index.md",
        "# Subj\n\n## Pages\n\n- [[Weird]]\n",
    )

    result = lint_mod.LintResult()
    lint_mod.lint(result, wiki_dir=wiki)

    unknown_warns = [w for w in result.warnings if "unknown type: weirdtype" in w]
    assert len(unknown_warns) == 1


# ── Orphan detection excludes _index.md (Fix 3) ─────────────────────


def test_index_md_not_flagged_as_orphan(lint_mod, tmp_path):
    """`_index.md` is not a link target by convention, so it must not
    surface as an orphan even when no page links to it."""
    wiki = make_wiki_root(tmp_path)
    long_body = "This page has plenty of content. " * 10
    write_page(wiki / "entities" / "Subj" / "2026-04" / "Alpha.md", body=long_body)
    write_page(
        wiki / "entities" / "Subj" / "_index.md",
        "# Subj\n\n## Pages\n\n- [[Alpha]]\n",
    )

    result = lint_mod.LintResult()
    lint_mod.lint(result, wiki_dir=wiki)

    orphan_warns = [w for w in result.warnings if "orphan page" in w]
    assert all(
        "_index" not in w for w in orphan_warns
    ), f"_index.md flagged as orphan: {orphan_warns}"


def test_index_sync_skips_when_no_pages_section(lint_mod, tmp_path):
    """Hubs lacking a ## Pages heading should be ignored by sync entirely.

    Other lint checks may still fire on the disk pages — we only assert
    that the sync check itself produces no listed/not-listed messages.
    """
    wiki = make_wiki_root(tmp_path)
    long_body = "This page has plenty of content. " * 10
    write_page(wiki / "entities" / "Subj" / "2026-04" / "Alpha.md", body=long_body)
    write_page(wiki / "entities" / "Subj" / "2026-04" / "Beta.md", body=long_body)
    # Hub has no ## Pages section — it's a template/empty hub.
    write_page(
        wiki / "entities" / "Subj" / "_index.md",
        "# Subj\n\nSome notes here without a Pages heading.\n",
    )

    result = lint_mod.LintResult()
    lint_mod.lint(result, wiki_dir=wiki)

    sync_errors = [e for e in result.errors if "_index.md lists" in e]
    sync_warns = [w for w in result.warnings if "not listed in" in w]
    assert sync_errors == [], f"unexpected sync errors: {sync_errors}"
    assert sync_warns == [], f"unexpected sync warns: {sync_warns}"


# ── Stem collision detection (issue #4 — pre-existing bug) ──────────


def test_stem_collision_errors_on_two_dirs(lint_mod, tmp_path):
    """Two .md files with the same stem in different dirs must both ERROR.

    Wikilink resolution becomes ambiguous and ``collect_pages`` previously
    silently overwrote one file's content with the other in a stem-keyed
    dict, hiding the loser from every subsequent lint check.
    """
    wiki = make_wiki_root(tmp_path)
    long_body = "This page has plenty of content. " * 10
    write_page(wiki / "concepts" / "Foo.md", body=long_body)
    write_page(wiki / "entities" / "Subj" / "2026-04" / "Foo.md", body=long_body)
    write_page(
        wiki / "entities" / "Subj" / "_index.md",
        "# Subj\n\n## Pages\n\n- [[Foo]]\n",
    )

    result = lint_mod.LintResult()
    lint_mod.lint(result, wiki_dir=wiki)

    collision_errors = [e for e in result.errors if "stem collision" in e]
    assert (
        len(collision_errors) == 2
    ), f"expected 2 collision errors, got {len(collision_errors)}: {collision_errors}"
    joined = "\n".join(collision_errors)
    assert "concepts/Foo.md" in joined
    assert "2026-04/Foo.md" in joined
    assert all("'Foo'" in e for e in collision_errors)


def test_stem_collision_excludes_index_md(lint_mod, tmp_path):
    """Multiple subject hubs share stem ``_index`` by design — no error."""
    wiki = make_wiki_root(tmp_path)
    long_body = "This page has plenty of content. " * 10
    write_page(wiki / "entities" / "SubjA" / "2026-04" / "PageA.md", body=long_body)
    write_page(
        wiki / "entities" / "SubjA" / "_index.md",
        "# SubjA\n\n## Pages\n\n- [[PageA]]\n",
    )
    write_page(wiki / "entities" / "SubjB" / "2026-04" / "PageB.md", body=long_body)
    write_page(
        wiki / "entities" / "SubjB" / "_index.md",
        "# SubjB\n\n## Pages\n\n- [[PageB]]\n",
    )

    result = lint_mod.LintResult()
    lint_mod.lint(result, wiki_dir=wiki)

    collision_errors = [e for e in result.errors if "stem collision" in e]
    assert (
        collision_errors == []
    ), f"_index hubs flagged as collisions: {collision_errors}"


def test_stem_collision_with_three_files(lint_mod, tmp_path):
    """Three colliding files: each ERROR must name the other two."""
    wiki = make_wiki_root(tmp_path)
    long_body = "This page has plenty of content. " * 10
    write_page(wiki / "concepts" / "Triple.md", body=long_body)
    write_page(wiki / "entities" / "SubjA" / "2026-04" / "Triple.md", body=long_body)
    write_page(wiki / "entities" / "SubjB" / "2026-04" / "Triple.md", body=long_body)
    write_page(
        wiki / "entities" / "SubjA" / "_index.md",
        "# SubjA\n\n## Pages\n\n- [[Triple]]\n",
    )
    write_page(
        wiki / "entities" / "SubjB" / "_index.md",
        "# SubjB\n\n## Pages\n\n- [[Triple]]\n",
    )

    result = lint_mod.LintResult()
    lint_mod.lint(result, wiki_dir=wiki)

    collision_errors = [e for e in result.errors if "stem collision" in e]
    assert len(collision_errors) == 3
    for err in collision_errors:
        assert "also used by" in err, f"error must list peers: {err}"
        peers_segment = err.split("also used by", 1)[1]
        other_triple_paths = peers_segment.count("Triple.md")
        assert (
            other_triple_paths == 2
        ), f"expected 2 peer paths in collision message: {err}"


def test_no_stem_collision_when_all_unique(lint_mod, tmp_path):
    """Distinct stems must not produce false-positive collision errors."""
    wiki = make_wiki_root(tmp_path)
    long_body = "This page has plenty of content. " * 10
    write_page(wiki / "concepts" / "Alpha.md", body=long_body)
    write_page(wiki / "entities" / "Subj" / "2026-04" / "Beta.md", body=long_body)
    write_page(
        wiki / "entities" / "Subj" / "_index.md",
        "# Subj\n\n## Pages\n\n- [[Beta]]\n",
    )

    result = lint_mod.LintResult()
    lint_mod.lint(result, wiki_dir=wiki)

    collision_errors = [e for e in result.errors if "stem collision" in e]
    assert collision_errors == []


def test_collect_pages_returns_paths_by_stem(lint_mod, tmp_path):
    """``collect_pages`` must expose every path per stem so callers can
    detect collisions that the legacy stem-keyed dict hides."""
    wiki = make_wiki_root(tmp_path)
    long_body = "This page has plenty of content. " * 5
    write_page(wiki / "concepts" / "Dup.md", body=long_body)
    write_page(wiki / "entities" / "Subj" / "2026-04" / "Dup.md", body=long_body)
    write_page(wiki / "entities" / "Subj" / "2026-04" / "Solo.md", body=long_body)

    pages, paths_by_stem = lint_mod.collect_pages(wiki_dir=wiki)

    assert "Dup" in pages
    assert "Solo" in pages
    assert len(paths_by_stem["Dup"]) == 2
    assert len(paths_by_stem["Solo"]) == 1
    dup_paths = sorted(str(p) for p in paths_by_stem["Dup"])
    assert any("concepts/Dup.md" in p for p in dup_paths)
    assert any("2026-04/Dup.md" in p for p in dup_paths)


# ── Issue #11: improvement enums + checklist task-list syntax ───────


PADDING_BODY = (
    "This is a real improvement page with enough body content to clear the "
    "stub threshold and any other length-based heuristics. "
)


def _improvement_fm(
    kind: str = "improvement",
    observed_at: str = "2026-05-08",
    domain: str = "cost",
    severity: str = "high",
    status: str = "open",
    related: list[str] | None = None,
) -> str:
    related = related if related is not None else []
    if not related:
        related_yaml = "[]"
    else:
        related_yaml = "\n" + "\n".join(f"  - {r}" for r in related)
    return (
        "---\n"
        "type: improvement\n"
        f"kind: {kind}\n"
        f'observed_at: "{observed_at}"\n'
        f"domain: {domain}\n"
        f"severity: {severity}\n"
        f"status: {status}\n"
        f"related: {related_yaml}\n"
        'created: "2026-05-08"\n'
        'updated: "2026-05-08"\n'
        "sources: []\n"
        "tags: []\n"
        "---\n"
    )


def _checklist_fm() -> str:
    return (
        "---\n"
        "type: checklist\n"
        'created: "2026-05-08"\n'
        'updated: "2026-05-08"\n'
        "sources: []\n"
        "tags: []\n"
        "---\n"
    )


def test_improvement_valid_passes(lint_mod, tmp_path):
    wiki = make_wiki_root(tmp_path)
    (wiki / "improvements" / "2026-05").mkdir(parents=True, exist_ok=True)
    write_page(
        wiki / "improvements" / "2026-05" / "GoodImpr.md",
        body="# Title\n\n" + PADDING_BODY,
        fm=_improvement_fm(),
    )

    result = lint_mod.LintResult()
    lint_mod.lint(result, wiki_dir=wiki)

    file_errors = [e for e in result.errors if "GoodImpr.md" in e]
    assert file_errors == [], f"unexpected errors for valid improvement: {file_errors}"


def test_improvement_invalid_kind_errors(lint_mod, tmp_path):
    wiki = make_wiki_root(tmp_path)
    (wiki / "improvements" / "2026-05").mkdir(parents=True, exist_ok=True)
    write_page(
        wiki / "improvements" / "2026-05" / "BadKind.md",
        body="# Title\n\n" + PADDING_BODY,
        fm=_improvement_fm(kind="garbage"),
    )

    result = lint_mod.LintResult()
    lint_mod.lint(result, wiki_dir=wiki)

    kind_errors = [e for e in result.errors if "BadKind.md" in e and "kind" in e]
    assert len(kind_errors) >= 1, f"expected kind error, got: {result.errors}"


def test_improvement_invalid_observed_at_errors(lint_mod, tmp_path):
    wiki = make_wiki_root(tmp_path)
    (wiki / "improvements" / "2026-05").mkdir(parents=True, exist_ok=True)
    write_page(
        wiki / "improvements" / "2026-05" / "BadDate.md",
        body="# Title\n\n" + PADDING_BODY,
        fm=_improvement_fm(observed_at="not-a-date"),
    )

    result = lint_mod.LintResult()
    lint_mod.lint(result, wiki_dir=wiki)

    date_errors = [e for e in result.errors if "BadDate.md" in e and "observed_at" in e]
    assert len(date_errors) >= 1, f"expected observed_at error, got: {result.errors}"


def test_improvement_invalid_domain_errors(lint_mod, tmp_path):
    wiki = make_wiki_root(tmp_path)
    (wiki / "improvements" / "2026-05").mkdir(parents=True, exist_ok=True)
    write_page(
        wiki / "improvements" / "2026-05" / "BadDomain.md",
        body="# Title\n\n" + PADDING_BODY,
        fm=_improvement_fm(domain="bogus"),
    )

    result = lint_mod.LintResult()
    lint_mod.lint(result, wiki_dir=wiki)

    domain_errors = [e for e in result.errors if "BadDomain.md" in e and "domain" in e]
    assert len(domain_errors) >= 1, f"expected domain error, got: {result.errors}"


def test_improvement_invalid_severity_errors(lint_mod, tmp_path):
    wiki = make_wiki_root(tmp_path)
    (wiki / "improvements" / "2026-05").mkdir(parents=True, exist_ok=True)
    write_page(
        wiki / "improvements" / "2026-05" / "BadSev.md",
        body="# Title\n\n" + PADDING_BODY,
        fm=_improvement_fm(severity="ultra"),
    )

    result = lint_mod.LintResult()
    lint_mod.lint(result, wiki_dir=wiki)

    sev_errors = [e for e in result.errors if "BadSev.md" in e and "severity" in e]
    assert len(sev_errors) >= 1, f"expected severity error, got: {result.errors}"


def test_improvement_invalid_status_errors(lint_mod, tmp_path):
    wiki = make_wiki_root(tmp_path)
    (wiki / "improvements" / "2026-05").mkdir(parents=True, exist_ok=True)
    write_page(
        wiki / "improvements" / "2026-05" / "BadStatus.md",
        body="# Title\n\n" + PADDING_BODY,
        fm=_improvement_fm(status="paused"),
    )

    result = lint_mod.LintResult()
    lint_mod.lint(result, wiki_dir=wiki)

    status_errors = [e for e in result.errors if "BadStatus.md" in e and "status" in e]
    assert len(status_errors) >= 1, f"expected status error, got: {result.errors}"


def test_improvement_related_missing_target_errors(lint_mod, tmp_path):
    wiki = make_wiki_root(tmp_path)
    (wiki / "improvements" / "2026-05").mkdir(parents=True, exist_ok=True)
    write_page(
        wiki / "improvements" / "2026-05" / "RelMissing.md",
        body="# Title\n\n" + PADDING_BODY,
        fm=_improvement_fm(related=["entities/Subj/2026-04/DoesNotExist.md"]),
    )

    result = lint_mod.LintResult()
    lint_mod.lint(result, wiki_dir=wiki)

    rel_errors = [e for e in result.errors if "RelMissing.md" in e and "related" in e]
    assert len(rel_errors) >= 1, f"expected related error, got: {result.errors}"


def test_improvement_related_existing_target_passes(lint_mod, tmp_path):
    wiki = make_wiki_root(tmp_path)
    long_body = "This page has plenty of content. " * 5
    write_page(wiki / "concepts" / "TargetConcept.md", body=long_body)

    (wiki / "improvements" / "2026-05").mkdir(parents=True, exist_ok=True)
    write_page(
        wiki / "improvements" / "2026-05" / "RelOk.md",
        body="# Title\n\n" + PADDING_BODY,
        fm=_improvement_fm(related=["TargetConcept"]),
    )

    result = lint_mod.LintResult()
    lint_mod.lint(result, wiki_dir=wiki)

    rel_errors = [e for e in result.errors if "related" in e]
    assert rel_errors == [], f"unexpected related errors: {rel_errors}"


def test_checklist_non_task_item_errors(lint_mod, tmp_path):
    wiki = make_wiki_root(tmp_path)
    (wiki / "checklists").mkdir(parents=True, exist_ok=True)
    body = (
        "# Title\n\n"
        "Intro paragraph long enough to clear the stub threshold for body length. "
        "More words to be safe and definitely past one hundred characters total.\n\n"
        "## Items\n"
        "- plain bullet\n"
    )
    write_page(
        wiki / "checklists" / "BadChecklist.md",
        body=body,
        fm=_checklist_fm(),
    )

    result = lint_mod.LintResult()
    lint_mod.lint(result, wiki_dir=wiki)

    item_errors = [
        e for e in result.errors if "BadChecklist.md" in e and "task-list" in e
    ]
    assert len(item_errors) >= 1, f"expected task-list error, got: {result.errors}"


def test_checklist_task_items_pass(lint_mod, tmp_path):
    wiki = make_wiki_root(tmp_path)
    (wiki / "checklists").mkdir(parents=True, exist_ok=True)
    body = (
        "# Title\n\n"
        "Intro paragraph long enough to clear the stub threshold for body length. "
        "More words to be safe and definitely past one hundred characters total.\n\n"
        "## Items\n"
        "- [ ] item1\n"
        "- [x] item2\n"
    )
    write_page(
        wiki / "checklists" / "GoodChecklist.md",
        body=body,
        fm=_checklist_fm(),
    )

    result = lint_mod.LintResult()
    lint_mod.lint(result, wiki_dir=wiki)

    item_errors = [e for e in result.errors if "task-list" in e]
    assert item_errors == [], f"unexpected task-list errors: {item_errors}"


# ── Issue #13: raw frontmatter required fields + immutability ───────


def make_data_root(tmp_path: Path) -> tuple[Path, Path]:
    data = tmp_path / "data"
    raw = data / "raw" / "github" / "issues"
    raw.mkdir(parents=True)
    wiki = data / "wiki"
    wiki.mkdir()
    return wiki, data / "raw"


RAW_FM_FULL = (
    "---\n"
    'source_url: "https://example.com/repo/issues/42"\n'
    "type: github_issue\n"
    'captured_at: "2026-05-08T09:00:00Z"\n'
    'contributor: "tester"\n'
    "tags: []\n"
    "---\n"
)

RAW_FM_MISSING_SOURCE_URL = (
    "---\n"
    "type: github_issue\n"
    'captured_at: "2026-05-08T09:00:00Z"\n'
    'contributor: "tester"\n'
    "tags: []\n"
    "---\n"
)


def _git_init_and_commit(repo_dir: Path, file_path: Path) -> None:
    env = {"GIT_TERMINAL_PROMPT": "0", "PATH": os.environ.get("PATH", "")}

    def run(*args: str) -> None:
        subprocess.run(args, cwd=repo_dir, check=True, capture_output=True, env=env)

    run("git", "init", "-q")
    rel = str(file_path.relative_to(repo_dir))
    run("git", "-c", "user.email=t@t", "-c", "user.name=t", "add", rel)
    run(
        "git",
        "-c",
        "user.email=t@t",
        "-c",
        "user.name=t",
        "commit",
        "-q",
        "-m",
        "init",
    )


def test_raw_missing_required_fm_errors(lint_mod, tmp_path):
    wiki, raw = make_data_root(tmp_path)
    target = raw / "github" / "issues" / "repo_42.md"
    target.write_text(RAW_FM_MISSING_SOURCE_URL + "\n# Body\n")

    result = lint_mod.LintResult()
    lint_mod.lint(result, wiki_dir=wiki, raw_dir=raw)

    src_errors = [e for e in result.errors if "repo_42.md" in e and "source_url" in e]
    assert len(src_errors) >= 1, f"expected source_url error, got: {result.errors}"


def test_raw_complete_fm_passes(lint_mod, tmp_path):
    wiki, raw = make_data_root(tmp_path)
    target = raw / "github" / "issues" / "repo_42.md"
    target.write_text(RAW_FM_FULL + "\n# Body\n")

    result = lint_mod.LintResult()
    lint_mod.lint(result, wiki_dir=wiki, raw_dir=raw)

    fm_errors = [
        e for e in result.errors if "repo_42.md" in e and "raw frontmatter missing" in e
    ]
    assert fm_errors == [], f"unexpected raw fm errors: {fm_errors}"


def test_raw_handoffs_skipped(lint_mod, tmp_path):
    wiki, raw = make_data_root(tmp_path)
    handoff_path = raw / "handoffs" / "2026" / "05" / "foo" / "research_handoff_01.md"
    handoff_path.parent.mkdir(parents=True, exist_ok=True)
    handoff_path.write_text("# no frontmatter at all\n")

    result = lint_mod.LintResult()
    lint_mod.lint(result, wiki_dir=wiki, raw_dir=raw)

    handoff_errors = [e for e in result.errors if "research_handoff_01.md" in e]
    assert handoff_errors == [], (
        "handoffs must be skipped by kb-lint-wiki (handled by kb-lint-handoff): "
        f"{handoff_errors}"
    )


def test_raw_captured_at_post_mtime_errors_when_strict(lint_mod, tmp_path):
    wiki, raw = make_data_root(tmp_path)
    target = raw / "github" / "issues" / "stale_capture.md"
    fm_old = (
        "---\n"
        'source_url: "https://example.com/x"\n'
        "type: github_issue\n"
        'captured_at: "2020-01-01T00:00:00Z"\n'
        'contributor: "tester"\n'
        "tags: []\n"
        "---\n"
    )
    target.write_text(fm_old + "\n# Body\n")
    now = time.time()
    os.utime(target, (now, now))

    result = lint_mod.LintResult()
    lint_mod.lint(result, wiki_dir=wiki, raw_dir=raw, check_immutability=True)

    drift_errors = [
        e for e in result.errors if "stale_capture.md" in e and "after captured_at" in e
    ]
    assert len(drift_errors) >= 1, f"expected drift error, got: {result.errors}"


def test_raw_captured_at_check_skipped_when_immutability_off(lint_mod, tmp_path):
    wiki, raw = make_data_root(tmp_path)
    target = raw / "github" / "issues" / "stale_capture.md"
    fm_old = (
        "---\n"
        'source_url: "https://example.com/x"\n'
        "type: github_issue\n"
        'captured_at: "2020-01-01T00:00:00Z"\n'
        'contributor: "tester"\n'
        "tags: []\n"
        "---\n"
    )
    target.write_text(fm_old + "\n# Body\n")
    now = time.time()
    os.utime(target, (now, now))

    result = lint_mod.LintResult()
    lint_mod.lint(result, wiki_dir=wiki, raw_dir=raw, check_immutability=False)

    drift_errors = [e for e in result.errors if "after captured_at" in e]
    assert (
        drift_errors == []
    ), f"mtime drift must not be reported when check_immutability=False: {drift_errors}"


def test_raw_immutability_via_git_errors(lint_mod, tmp_path):
    wiki, raw = make_data_root(tmp_path)
    data_dir = raw.parent
    target = raw / "github" / "issues" / "tracked.md"
    target.write_text(RAW_FM_FULL + "\n# Original\n")
    now = time.time()
    os.utime(target, (now, now))

    _git_init_and_commit(data_dir, target)

    target.write_text(RAW_FM_FULL + "\n# Modified\n")
    os.utime(target, (now, now))

    result = lint_mod.LintResult()
    lint_mod.lint(result, wiki_dir=wiki, raw_dir=raw, check_immutability=True)

    immut_errors = [
        e for e in result.errors if "tracked.md" in e and "modified after creation" in e
    ]
    assert (
        len(immut_errors) >= 1
    ), f"expected immutability violation, got: {result.errors}"


def test_raw_immutability_no_git_no_crash(lint_mod, tmp_path):
    wiki, raw = make_data_root(tmp_path)
    target = raw / "github" / "issues" / "untracked.md"
    target.write_text(RAW_FM_FULL + "\n# Body\n")
    now = time.time()
    os.utime(target, (now, now))

    result = lint_mod.LintResult()
    lint_mod.lint(result, wiki_dir=wiki, raw_dir=raw, check_immutability=True)

    immut_errors = [e for e in result.errors if "modified after creation" in e]
    assert (
        immut_errors == []
    ), f"no git → immutability check must be silent, got: {immut_errors}"


def test_raw_immutability_skipped_when_off(lint_mod, tmp_path):
    wiki, raw = make_data_root(tmp_path)
    data_dir = raw.parent
    target = raw / "github" / "issues" / "tracked.md"
    target.write_text(RAW_FM_FULL + "\n# Original\n")
    now = time.time()
    os.utime(target, (now, now))

    _git_init_and_commit(data_dir, target)

    target.write_text(RAW_FM_FULL + "\n# Modified\n")
    os.utime(target, (now, now))

    result = lint_mod.LintResult()
    lint_mod.lint(result, wiki_dir=wiki, raw_dir=raw, check_immutability=False)

    immut_errors = [e for e in result.errors if "modified after creation" in e]
    assert (
        immut_errors == []
    ), f"check_immutability=False → no immutability errors, got: {immut_errors}"


# ── _get_modified_raw_files: porcelain status code parser ───────────


def test_get_modified_raw_files_returns_none_without_git(lint_mod, tmp_path):
    """No .git dir → return None silently (no immutability gate possible)."""
    (tmp_path / "raw").mkdir()
    assert lint_mod._get_modified_raw_files(tmp_path) is None


def test_get_modified_raw_files_classifies_status_codes(lint_mod, tmp_path):
    """Validate the porcelain status-code parser end-to-end via real git.

    Sets up: one committed-then-modified file (`M`), one staged-modified
    file (` M` after `git add`-then-edit becomes `MM`), one staged-added
    file (`A `), one untracked (`??`), and one deleted (` D`). Only the
    first three modify-shaped entries are expected as violations; `A`
    and `??` are NEW and must be excluded.
    """
    raw = tmp_path / "raw" / "github" / "issues"
    raw.mkdir(parents=True)
    committed = raw / "committed.md"
    deleted = raw / "deleted.md"
    committed.write_text(RAW_FM_FULL + "\n# Original\n")
    deleted.write_text(RAW_FM_FULL + "\n# Will be removed\n")

    env = {"GIT_TERMINAL_PROMPT": "0", "PATH": os.environ.get("PATH", "")}

    def run(*args: str) -> None:
        subprocess.run(args, cwd=tmp_path, check=True, capture_output=True, env=env)

    run("git", "init", "-q")
    run("git", "-c", "user.email=t@t", "-c", "user.name=t", "add", "raw/")
    run(
        "git",
        "-c",
        "user.email=t@t",
        "-c",
        "user.name=t",
        "commit",
        "-q",
        "-m",
        "init",
    )

    committed.write_text(RAW_FM_FULL + "\n# Modified\n")
    deleted.unlink()
    untracked = raw / "untracked.md"
    untracked.write_text(RAW_FM_FULL + "\n# Brand new\n")
    added = raw / "added.md"
    added.write_text(RAW_FM_FULL + "\n# Staged add\n")
    run(
        "git",
        "-c",
        "user.email=t@t",
        "-c",
        "user.name=t",
        "add",
        str(added.relative_to(tmp_path)),
    )

    modified = lint_mod._get_modified_raw_files(tmp_path)

    assert modified is not None
    rels = sorted(p.relative_to(tmp_path).as_posix() for p in modified)
    assert "raw/github/issues/committed.md" in rels
    assert "raw/github/issues/deleted.md" in rels
    assert "raw/github/issues/untracked.md" not in rels
    assert "raw/github/issues/added.md" not in rels
