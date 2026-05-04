#!/usr/bin/env python3
"""
Wiki linter — health check for the KnowledgeBase vault.

Checks:
  1. Dead wikilinks (link target doesn't exist)
  2. .md extension in wikilink targets (Obsidian doesn't need it)
  3. Self-referencing links
  4. LaTeX/HTML in content (Obsidian markdown only)
  5. Unfilled LLM placeholders (<!-- LLM TODO: -->)
  6. Frontmatter format (missing/invalid, quoted types, inline sources,
     missing/unknown type, missing required fields)
  7. Empty () in Relationships section
  8. Empty sections (heading with no content before next heading)
  9. Stale sources (sources reference non-existent raw files)
 10. Stub pages (body length below STUB_THRESHOLD_CHARS)
 11. Orphan pages (no inbound links from other wiki pages)
 12. Subject _index.md ↔ disk sync (listed pages exist, on-disk pages listed)

Usage:
    python3 scripts/lint-wiki.py           # full lint
    python3 scripts/lint-wiki.py --strict  # exit code 1 on any warning
"""

import re
import sys
from pathlib import Path

BASEDIR = Path(__file__).resolve().parent.parent.parent.parent
WIKI_DIR = BASEDIR / "wiki"
RAW_DIR = BASEDIR / "raw"

# Body length (after frontmatter) below this is flagged as a stub page.
STUB_THRESHOLD_CHARS = 100

REQUIRED_FM_FIELDS = {
    "entity": ["type", "created", "updated", "sources", "tags"],
    "concept": ["type", "created", "updated", "sources", "tags"],
    "decision": ["type", "created", "updated", "sources", "tags"],
    "summary": ["type", "created", "updated", "sources", "tags"],
    "question": ["type", "created", "updated", "sources", "tags"],
    "index": ["type", "created", "updated"],
}

COLLISION_EXEMPT_STEMS = frozenset({"_index", "index"})


class LintResult:
    def __init__(self):
        self.errors: list[str] = []    # must fix
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

        print(f"\n--- Summary ---\n")
        print(f"  Errors:   {len(self.errors)}")
        print(f"  Warnings: {len(self.warnings)}")


def parse_frontmatter(content: str) -> dict | None:
    """Extract frontmatter fields from markdown content (no yaml dependency)."""
    if not content.startswith("---"):
        return None
    parts = content.split("---", 2)
    if len(parts) < 3:
        return None
    fm_text = parts[1].strip()
    if not fm_text:
        return {}
    result = {}
    current_key = None
    current_list = None
    for line in fm_text.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        # List item under current key
        if stripped.startswith("- ") and current_key:
            if current_list is None:
                current_list = []
                result[current_key] = current_list
            current_list.append(stripped[2:].strip().strip('"').strip("'"))
            continue
        # Key: value
        m = re.match(r"^([a-zA-Z_]+)\s*:\s*(.*)", stripped)
        if m:
            current_key = m.group(1)
            val = m.group(2).strip()
            current_list = None
            if val == "" or val == "[]":
                result[current_key] = []
            elif val.startswith("["):
                # Inline list
                items = val.strip("[]").split(",")
                result[current_key] = [i.strip().strip('"').strip("'") for i in items if i.strip()]
            elif val.startswith('"') or val.startswith("'"):
                result[current_key] = val.strip('"').strip("'")
            else:
                result[current_key] = val
    return result


def get_raw_frontmatter(content: str) -> str:
    """Get raw frontmatter string for format checks."""
    if not content.startswith("---"):
        return ""
    parts = content.split("---", 2)
    return parts[1] if len(parts) >= 3 else ""


def collect_pages(
    wiki_dir: Path = None,
) -> tuple[dict[str, str], dict[str, list[Path]]]:
    """Return ``(pages, paths_by_stem)``: stem→first content (Obsidian
    wikilinks resolve by stem alone), and stem→every path sharing the
    stem so the lint pass can flag collisions the legacy dict hides."""
    wiki_dir = wiki_dir if wiki_dir is not None else WIKI_DIR
    pages: dict[str, str] = {}
    paths_by_stem: dict[str, list[Path]] = {}
    for f in wiki_dir.rglob("*.md"):
        paths_by_stem.setdefault(f.stem, []).append(f)
        if f.stem not in pages:
            pages[f.stem] = f.read_text()
    return pages, paths_by_stem


def extract_links(content: str) -> list[str]:
    """Extract wikilink targets from content."""
    return re.findall(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]", content)


def lint(result: LintResult, wiki_dir: Path = None) -> None:
    wiki_dir = wiki_dir if wiki_dir is not None else WIKI_DIR
    # data_dir is wiki_dir.parent (project root) so that frontmatter `sources:`
    # resolve correctly even when tests pass a tmp wiki_dir.
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
        body = content.split("---", 2)[2] if content.startswith("---") and content.count("---") >= 2 else content

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

        # ── 4. LaTeX / HTML ─────────────────────────────────────────────
        if re.search(r"\$[^$]+\$", body):
            result.error(rel, "contains LaTeX ($...$) — use plain text arrows (→)")
        if re.search(r"\\rightarrow|\\leftarrow|\\times|\\frac", body):
            result.error(rel, "contains LaTeX commands — use Obsidian markdown only")
        if re.search(r"<(?!!--)[a-zA-Z]", body):
            # Allow <!-- comments --> but flag <div>, <span>, etc.
            html_tags = re.findall(r"<([a-zA-Z]+)", body)
            non_comment = [t for t in html_tags if t not in ("br",)]
            if non_comment:
                result.warn(rel, f"contains HTML tags: {', '.join(set(non_comment))}")

        # ── 5. Unfilled placeholders ────────────────────────────────────
        # Accept both `<!-- LLM: -->` (legacy) and `<!-- LLM TODO: -->`
        # (current skeleton_gen.py output) so the source-of-truth template
        # stays in sync with what the linter detects.
        placeholders = re.findall(r"<!--\s*LLM(?:\s+TODO)?:.*?-->", body)
        if placeholders:
            result.warn(rel, f"{len(placeholders)} unfilled <!-- LLM TODO: --> placeholder(s)")

        # ── 6. Frontmatter format ───────────────────────────────────────
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

        # ── 7. Empty relation parens ────────────────────────────────────
        if "## Relationships" in body:
            rel_section = body.split("## Relationships")[1].split("##")[0]
            if "()" in rel_section:
                result.warn(rel, "empty () in Relationships section")

        # ── 8. Empty sections ───────────────────────────────────────────
        headings = list(re.finditer(r"^##\s+.+$", body, re.MULTILINE))
        for i, match in enumerate(headings):
            start = match.end()
            end = headings[i + 1].start() if i + 1 < len(headings) else len(body)
            section_content = body[start:end].strip()
            # Skip if it's just a placeholder comment
            if not section_content:
                heading_text = match.group().strip()
                result.warn(rel, f"empty section: {heading_text}")

        # ── 9. Stale sources ────────────────────────────────────────────
        sources = fm.get("sources", [])
        if isinstance(sources, list):
            for src in sources:
                if isinstance(src, str) and src:
                    src_path = data_dir / src
                    if not src_path.exists():
                        result.error(rel, f"source file not found: {src}")

        # ── 10. Stub pages ──────────────────────────────────────────────
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

    # ── 11. Orphan pages ────────────────────────────────────────────────
    # Subject hubs (`_index.md`) are not link targets by convention
    # (cf. skeleton_gen._index_wiki_pages: files starting with `_` are
    # excluded from the link index), so they cannot accumulate inbound
    # links and must be excluded from orphan detection.
    for stem in all_stems:
        if stem in ("index", "_index"):
            continue
        if not inbound.get(stem):
            result.warn(_find_relative(stem, wiki_dir), "orphan page — no inbound links")

    # ── 12. Subject _index.md ↔ disk sync ───────────────────────────────
    check_index_sync(result, wiki_dir)


def _find_relative(stem: str, wiki_dir: Path = None) -> str:
    """Find relative path for a page stem."""
    wiki_dir = wiki_dir if wiki_dir is not None else WIKI_DIR
    for f in wiki_dir.rglob("*.md"):
        if f.stem == stem:
            return str(f.relative_to(wiki_dir))
    return stem


def check_index_sync(result: LintResult, wiki_dir: Path = None) -> None:
    """Verify that each subject's _index.md lists exactly the pages that exist on disk.

    For every entities/{subject}/_index.md:
      - listed_but_missing → ERROR (broken hub)
      - on_disk_not_listed → WARN  (page exists but not advertised in the hub)

    Scope constraint: wikilinks are extracted ONLY from the ``## Pages``
    section, after fenced code blocks (``` ... ``` and ~~~ ... ~~~) are
    stripped. Links elsewhere in the hub body (notes, references, prompt
    templates) are intentionally ignored to avoid false positives. If the hub
    has no ``## Pages`` heading, the sync check is skipped entirely for that
    hub — empty/template hubs shouldn't flood the output.
    """
    wiki_dir = wiki_dir if wiki_dir is not None else WIKI_DIR
    entities_root = wiki_dir / "entities"
    if not entities_root.exists():
        return

    for index_file in entities_root.rglob("_index.md"):
        subject_dir = index_file.parent
        subject = subject_dir.name
        rel_index = str(index_file.relative_to(wiki_dir))

        raw_text = index_file.read_text()

        # Strip fenced code blocks so wikilinks inside templates / examples
        # are not mistaken for hub entries.
        stripped = re.sub(r"```.*?```", "", raw_text, flags=re.DOTALL)
        stripped = re.sub(r"~~~.*?~~~", "", stripped, flags=re.DOTALL)

        # Limit scope to the ## Pages section (heading inclusive, up to the
        # next ## heading or EOF). If the hub has no Pages heading at all,
        # skip sync entirely.
        pages_match = re.search(r"^##\s+Pages\b.*$", stripped, re.MULTILINE)
        if not pages_match:
            continue

        section_start = pages_match.end()
        next_heading = re.search(r"^##\s+", stripped[section_start:], re.MULTILINE)
        section_end = (
            section_start + next_heading.start()
            if next_heading
            else len(stripped)
        )
        pages_section = stripped[section_start:section_end]

        listed_stems = set(extract_links(pages_section))

        on_disk_stems = {
            f.stem
            for f in subject_dir.rglob("*.md")
            if f.stem != "_index"
        }

        # Filter wikilinks to only those that look like they target a subject
        # page (no "/" in the link → simple stem reference).
        # Also drop self-link to _index.
        listed_stems = {
            link for link in listed_stems
            if "/" not in link and link != "_index"
        }

        listed_but_missing = listed_stems - on_disk_stems
        on_disk_not_listed = on_disk_stems - listed_stems

        for stem in sorted(listed_but_missing):
            result.error(
                rel_index,
                f"_index.md lists [[{stem}]] but no file with that stem under {subject_dir.relative_to(wiki_dir)}",
            )

        for stem in sorted(on_disk_not_listed):
            page_rel = _find_relative(stem, wiki_dir)
            result.warn(
                page_rel,
                f"page not listed in {subject}/_index.md",
            )


def main():
    strict = "--strict" in sys.argv

    print("Linting wiki/...\n")

    result = LintResult()
    lint(result)
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
