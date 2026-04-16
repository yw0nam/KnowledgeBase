#!/usr/bin/env python3
"""
Wiki linter — health check for the KnowledgeBase vault.

Checks:
  1. Dead wikilinks (link target doesn't exist)
  2. .md extension in wikilink targets (Obsidian doesn't need it)
  3. Self-referencing links
  4. LaTeX/HTML in content (Obsidian markdown only)
  5. Unfilled LLM placeholders (<!-- LLM: -->)
  6. Frontmatter format (inline sources, quoted types, missing fields)
  7. Orphan pages (no inbound links from other wiki pages)
  8. Missing frontmatter entirely
  9. Empty sections (heading with no content before next heading)
 10. Stale pages (sources reference non-existent raw files)

Usage:
    python3 scripts/lint-wiki.py           # full lint
    python3 scripts/lint-wiki.py --strict  # exit code 1 on any warning
"""

import re
import sys
from pathlib import Path

BASEDIR = Path(__file__).parent.parent
DATADIR = BASEDIR / "data"
WIKI_DIR = DATADIR / "wiki"
RAW_DIR = DATADIR / "raw"

REQUIRED_FM_FIELDS = {
    "entity": ["type", "created", "updated", "sources", "graph_nodes", "tags"],
    "concept": ["type", "created", "updated", "sources", "graph_nodes", "tags"],
    "decision": ["type", "created", "updated", "sources", "tags"],
    "summary": ["type", "created", "updated", "sources", "tags"],
    "question": ["type", "created", "updated", "sources", "tags"],
    "index": ["type", "created", "updated"],
}


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


def collect_pages() -> dict[str, str]:
    """Collect all wiki pages: {stem: content}."""
    pages = {}
    for f in WIKI_DIR.rglob("*.md"):
        pages[f.stem] = f.read_text()
    return pages


def extract_links(content: str) -> list[str]:
    """Extract wikilink targets from content."""
    return re.findall(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]", content)


def lint(result: LintResult):
    pages = collect_pages()
    all_stems = set(pages.keys())

    # Build inbound link map for orphan detection
    inbound: dict[str, set[str]] = {stem: set() for stem in all_stems}

    for stem, content in pages.items():
        rel = _find_relative(stem)
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
        placeholders = re.findall(r"<!--\s*LLM:.*?-->", body)
        if placeholders:
            result.warn(rel, f"{len(placeholders)} unfilled <!-- LLM: --> placeholder(s)")

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

        # Missing required fields
        page_type = fm.get("type", "")
        required = REQUIRED_FM_FIELDS.get(page_type, [])
        for field in required:
            if field not in fm:
                result.error(rel, f"missing frontmatter field: {field}")

        # Empty graph_nodes (non-index pages)
        if page_type in ("entity", "concept"):
            gn = fm.get("graph_nodes", [])
            if not gn or gn == []:
                result.warn(rel, "graph_nodes is empty")

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
                    src_path = BASEDIR / src
                    if not src_path.exists():
                        result.error(rel, f"source file not found: {src}")

    # ── 10. Orphan pages ────────────────────────────────────────────────
    for stem in all_stems:
        if stem == "index":
            continue
        if not inbound.get(stem):
            result.warn(_find_relative(stem), "orphan page — no inbound links")


def _find_relative(stem: str) -> str:
    """Find relative path for a page stem."""
    for f in WIKI_DIR.rglob("*.md"):
        if f.stem == stem:
            return str(f.relative_to(WIKI_DIR))
    return stem


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
