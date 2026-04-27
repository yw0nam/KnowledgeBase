"""Tests for scripts/lint-wiki.py — stub + index sync checks."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
LINT_PATH = REPO_ROOT / "scripts" / "lint-wiki.py"


def _load_lint_module():
    """Load scripts/lint-wiki.py as a module (filename has a hyphen)."""
    spec = importlib.util.spec_from_file_location("lint_wiki", LINT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["lint_wiki"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def lint_mod():
    return _load_lint_module()


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
        "# Subj\n\n- [[Tiny]]\n",
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
        "# Subj\n\n- [[Big]]\n",
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
    write_page(wiki / "entities" / "Subj" / "_index.md", "[[Big]]")

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
        "# Subj\n\n- [[PageOne]]\n",
    )

    result = lint_mod.LintResult()
    lint_mod.lint(result, wiki_dir=wiki)

    sync_errors = [
        e for e in result.errors
        if "_index.md lists [[PageOne]]" in e
    ]
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
        "# Subj\n\n- [[Listed]]\n",
    )

    result = lint_mod.LintResult()
    lint_mod.lint(result, wiki_dir=wiki)

    sync_warns = [
        w for w in result.warnings
        if "page not listed in Subj/_index.md" in w
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
        "# Subj\n\n- [[Alpha]]\n- [[Beta]]\n",
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
        "# Subj\n\n- [[Alpha]]\n",
    )

    result = lint_mod.LintResult()
    lint_mod.lint(result, wiki_dir=wiki)

    assert result.errors == [], f"unexpected errors: {result.errors}"
