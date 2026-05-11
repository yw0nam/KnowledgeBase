#!/usr/bin/env python3
"""
Wiki linter — health check for the KnowledgeBase vault.

Checks:
  1. Dead wikilinks (link target doesn't exist)
  2. .md extension in wikilink targets (Obsidian doesn't need it)
  3. Self-referencing links
  4. Unfilled LLM placeholders (<!-- LLM TODO: -->)
  5. Frontmatter format (missing/invalid, quoted types, inline sources,
     missing/unknown type, missing required fields)
  6. Empty () in Relationships section
  7. Empty sections (heading with no content before next heading)
  8. Stale sources (sources reference non-existent raw files)
  9. Stub pages (body length below STUB_THRESHOLD_CHARS)
 10. Orphan pages (no inbound links from other wiki pages)
 11. Subject _index.md ↔ disk sync (listed pages exist, on-disk pages listed)
 12. Improvement enum validation (kind, observed_at, domain, severity, status,
     related path resolution)
 13. Checklist items must use markdown task-list syntax under ``## Items``
 14. Raw frontmatter required fields (source_url, type, captured_at,
     contributor) — always-on, scoped to raw ingest categories
 15. Raw immutability — ``--check-immutability`` opts in to:
       a) git-status modified-but-not-new files under data/raw/ → ERROR
       b) file mtime later than captured_at by more than the tolerance → ERROR

Usage:
    uv run python -m kb_mcp.cli.lint_wiki                       # full lint
    uv run python -m kb_mcp.cli.lint_wiki --strict              # warnings → errors + immutability on
    uv run python -m kb_mcp.cli.lint_wiki --check-immutability  # immutability checks only
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from kb_mcp.cli._wiki_checks import (
    CAPTURED_AT_MTIME_TOLERANCE_SEC,
    RAW_FM_REQUIRED,
    RAW_INGEST_TOPLEVEL,
    check_index_sync,
    check_raw_captured_at_mtime,
    check_raw_frontmatter,
    check_raw_immutability,
    _get_modified_raw_files,
)
from kb_mcp.cli._wiki_utils import (
    _find_relative,
    _parse_yaml_frontmatter,
    collect_pages,
    extract_links,
    get_raw_frontmatter,
    parse_frontmatter,
)
from kb_mcp.cli._wiki_validators import (
    IMPROVEMENT_DOMAIN_VALUES,
    IMPROVEMENT_KIND_VALUES,
    IMPROVEMENT_SEVERITY_VALUES,
    IMPROVEMENT_STATUS_VALUES,
    ISO_DATE_RE,
    _validate_checklist_items,
    _validate_improvement_fm,
)

__all__ = [
    "BASEDIR",
    "CAPTURED_AT_MTIME_TOLERANCE_SEC",
    "COLLISION_EXEMPT_STEMS",
    "IMPROVEMENT_DOMAIN_VALUES",
    "IMPROVEMENT_KIND_VALUES",
    "IMPROVEMENT_SEVERITY_VALUES",
    "IMPROVEMENT_STATUS_VALUES",
    "ISO_DATE_RE",
    "LintResult",
    "RAW_DIR",
    "RAW_FM_REQUIRED",
    "RAW_INGEST_TOPLEVEL",
    "REQUIRED_FM_FIELDS",
    "STUB_THRESHOLD_CHARS",
    "WIKI_DIR",
    "_find_relative",
    "_get_modified_raw_files",
    "_parse_yaml_frontmatter",
    "_validate_checklist_items",
    "_validate_improvement_fm",
    "check_index_sync",
    "check_raw_captured_at_mtime",
    "check_raw_frontmatter",
    "check_raw_immutability",
    "collect_pages",
    "extract_links",
    "get_raw_frontmatter",
    "lint",
    "main",
    "parse_frontmatter",
]

BASEDIR = Path(__file__).resolve().parent.parent.parent.parent
WIKI_DIR = BASEDIR / "data" / "wiki"
RAW_DIR = BASEDIR / "data" / "raw"

# Body length (after frontmatter) below this is flagged as a stub page.
STUB_THRESHOLD_CHARS = 100

REQUIRED_FM_FIELDS = {
    "entity": ["type", "created", "updated", "sources", "tags"],
    "concept": ["type", "created", "updated", "sources", "tags"],
    "decision": ["type", "created", "updated", "sources", "tags"],
    # Improvement adds the lifecycle/severity/domain triplet plus
    # observation timestamp and back-references; enums are checked by
    # ``_validate_improvement_fm`` after the required-field loop.
    "improvement": [
        "type",
        "kind",
        "observed_at",
        "domain",
        "severity",
        "status",
        "related",
        "created",
        "updated",
        "sources",
        "tags",
    ],
    "checklist": ["type", "created", "updated", "sources", "tags"],
    "summary": ["type", "created", "updated", "sources", "tags"],
    "question": ["type", "created", "updated", "sources", "tags"],
    "index": ["type", "created", "updated"],
}

COLLISION_EXEMPT_STEMS = frozenset({"_index"})


class LintResult:
    def __init__(self):
        self.errors: list[str] = []  # must fix
        self.warnings: list[str] = []  # should fix

    def error(self, file: str, msg: str):
        self.errors.append(f"  ERROR   {file}: {msg}")

    def warn(self, file: str, msg: str):
        self.warnings.append(f"  WARN    {file}: {msg}")

    @property
    def ok(self) -> bool:
        return len(self.errors) == 0

    def print_report(self):
        total = len(self.errors) + len(self.warnings)
        if total == 0:
            print("All checks passed.")
            return

        if self.errors:
            print(f"\n--- Errors ({len(self.errors)}) ---\n")
            for e in sorted(self.errors):
                print(e)

        if self.warnings:
            print(f"\n--- Warnings ({len(self.warnings)}) ---\n")
            for w in sorted(self.warnings):
                print(w)

        print("\n--- Summary ---\n")
        print(f"  Errors:   {len(self.errors)}")
        print(f"  Warnings: {len(self.warnings)}")


def lint(
    result: LintResult,
    wiki_dir: Path = None,
    raw_dir: Path = None,
    check_immutability: bool = False,
) -> None:
    wiki_dir = wiki_dir if wiki_dir is not None else WIKI_DIR
    raw_dir = raw_dir if raw_dir is not None else RAW_DIR
    data_dir = wiki_dir.parent

    pages, paths_by_stem = collect_pages(wiki_dir)
    all_stems = set(pages.keys())

    # ── 0. Stem collisions ──────────────────────────────────────────────
    # Obsidian wikilinks are stem-keyed, so two pages sharing a stem make
    # ``[[Foo]]`` ambiguous and used to silently drop one file from
    # ``pages`` entirely. Subject hubs (``_index.md``) intentionally share
    # their stem across subjects and are exempt.
    for stem, paths in paths_by_stem.items():
        if stem in COLLISION_EXEMPT_STEMS or len(paths) <= 1:
            continue
        rel_paths = sorted(str(p.relative_to(wiki_dir)) for p in paths)
        for rel_path in rel_paths:
            others = [op for op in rel_paths if op != rel_path]
            result.error(
                rel_path,
                f"stem collision: '{stem}' also used by {', '.join(others)}",
            )

    # Build inbound link map for orphan detection
    inbound: dict[str, set[str]] = {stem: set() for stem in all_stems}

    for stem, content in pages.items():
        rel = _find_relative(stem, wiki_dir)
        links = extract_links(content)
        fm_raw = get_raw_frontmatter(content)
        fm = parse_frontmatter(content)
        body = (
            content.split("---", 2)[2]
            if content.startswith("---") and content.count("---") >= 2
            else content
        )

        # ── 1. Dead wikilinks ───────────────────────────────────────────
        for link in links:
            if link in all_stems:
                inbound[link].add(stem)
            else:
                result.error(rel, f"dead link [[{link}]]")

        # ── 2. .md in link target ───────────────────────────────────────
        for link in links:
            if ".md" in link:
                result.error(rel, f"wikilink contains .md extension: [[{link}]]")

        # ── 3. Self-links ───────────────────────────────────────────────
        for link in links:
            if link == stem:
                result.warn(rel, "links to itself")

        # ── 4. Unfilled placeholders ────────────────────────────────────
        # Accept both `<!-- LLM: -->` (legacy) and `<!-- LLM TODO: -->`
        # (canonical wiki template marker) so the lint stays aligned with
        # what wiki templates emit.
        placeholders = re.findall(r"<!--\s*LLM(?:\s+TODO)?:.*?-->", body)
        if placeholders:
            result.warn(
                rel, f"{len(placeholders)} unfilled <!-- LLM TODO: --> placeholder(s)"
            )

        # ── 5. Frontmatter format ───────────────────────────────────────
        if fm is None:
            result.error(rel, "missing or invalid frontmatter")
            continue

        # Quoted type values
        if re.search(r'type:\s*"', fm_raw):
            result.error(rel, 'type value is quoted ("entity") — should be unquoted')

        # Inline list style for sources
        if re.search(r"sources:\s*\[", fm_raw):
            sources_inline = fm_raw.split("sources:")[1].split("\n")[0].strip()
            if sources_inline != "[]":
                result.error(rel, "sources uses inline [...] format — use block style")

        # Missing or unknown type (must come before required-field loop —
        # an empty/unknown type silently disables the loop otherwise).
        page_type = fm.get("type", "")
        if not page_type:
            result.error(rel, "missing frontmatter field: type")
        elif page_type not in REQUIRED_FM_FIELDS:
            result.warn(rel, f"unknown type: {page_type}")

        # Missing required fields
        required = REQUIRED_FM_FIELDS.get(page_type, [])
        for field in required:
            if field not in fm:
                result.error(rel, f"missing frontmatter field: {field}")

        if page_type == "improvement":
            _validate_improvement_fm(rel, fm, result, all_stems, wiki_dir)
        elif page_type == "checklist":
            _validate_checklist_items(rel, body, result)

        # ── 6. Empty relation parens ────────────────────────────────────
        if "## Relationships" in body:
            rel_section = body.split("## Relationships")[1].split("##")[0]
            if "()" in rel_section:
                result.warn(rel, "empty () in Relationships section")

        # ── 7. Empty sections ───────────────────────────────────────────
        headings = list(re.finditer(r"^##\s+.+$", body, re.MULTILINE))
        for i, match in enumerate(headings):
            start = match.end()
            end = headings[i + 1].start() if i + 1 < len(headings) else len(body)
            section_content = body[start:end].strip()
            # Skip if it's just a placeholder comment
            if not section_content:
                heading_text = match.group().strip()
                result.warn(rel, f"empty section: {heading_text}")

        # ── 8. Stale sources ────────────────────────────────────────────
        sources = fm.get("sources", [])
        if isinstance(sources, list):
            for src in sources:
                if isinstance(src, str) and src:
                    src_path = data_dir / src
                    if not src_path.exists():
                        result.error(rel, f"source file not found: {src}")

        # ── 9. Stub pages ───────────────────────────────────────────────
        # Subject hubs at entities/{subject}/_index.md are excluded — they're
        # allowed to be short, check_index_sync handles them separately. Other
        # files happening to be named _index.md (outside entities/) still get
        # the stub check.
        rel_posix = rel.replace("\\", "/")
        is_subject_hub = stem == "_index" and "entities/" in rel_posix
        if not is_subject_hub:
            if len(body.strip()) < STUB_THRESHOLD_CHARS:
                result.warn(
                    rel,
                    f"stub page — body {len(body.strip())} chars (< {STUB_THRESHOLD_CHARS})",
                )

    # ── 10. Orphan pages ────────────────────────────────────────────────
    # Subject hubs (`_index.md`) are not link targets by convention
    # (files starting with `_` are excluded from the link index by
    # convention), so they cannot accumulate inbound links and must be
    # excluded from orphan detection.
    for stem in all_stems:
        if stem in ("index", "_index"):
            continue
        if not inbound.get(stem):
            result.warn(
                _find_relative(stem, wiki_dir), "orphan page — no inbound links"
            )

    # ── 11. Subject _index.md ↔ disk sync ───────────────────────────────
    check_index_sync(result, wiki_dir)

    # ── 12. Raw frontmatter required fields (always-on) ─────────────────
    check_raw_frontmatter(result, raw_dir)

    # ── 13. Raw immutability (opt-in: --check-immutability or --strict) ─
    if check_immutability:
        check_raw_captured_at_mtime(result, raw_dir)
        check_raw_immutability(result, raw_dir, data_dir)


def main():
    strict = "--strict" in sys.argv
    check_immutability = "--check-immutability" in sys.argv or strict

    print("Linting wiki/...\n")

    result = LintResult()
    lint(result, check_immutability=check_immutability)
    result.print_report()

    if not result.ok:
        print("\nFAILED — fix errors before committing.")
        sys.exit(1)
    elif strict and result.warnings:
        print("\nFAILED (--strict) — warnings treated as errors.")
        sys.exit(1)
    else:
        print("\nPASSED")
        sys.exit(0)


if __name__ == "__main__":
    main()
