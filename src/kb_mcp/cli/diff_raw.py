#!/usr/bin/env python3
"""
diff_raw.py — detect raw files not yet referenced by wiki pages.

Scans data/raw/ directory and identifies files that are not yet cited in any
wiki page's frontmatter `sources:` list. These are candidates for wiki page
creation.

Usage:
    uv run python -m kb_mcp.cli.diff_raw [--raw-dir data/raw] [--wiki-dir data/wiki]

Output (one relative path per line):
    data/raw/github/nanobot_runtime/issue/42-some-title.md

Exit codes:
    0  unprocessed files found (printed to stdout)
    1  no unprocessed files
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _collect_wiki_sources(wiki_dir: Path) -> set[str]:
    """Collect all source paths referenced in wiki frontmatter."""
    sources: set[str] = set()
    if not wiki_dir.exists():
        return sources
    for f in wiki_dir.rglob("*.md"):
        try:
            content = f.read_text(encoding="utf-8")
        except OSError:
            continue
        if not content.startswith("---"):
            continue
        parts = content.split("---", 2)
        if len(parts) < 3:
            continue
        fm = parts[1]
        in_sources = False
        for line in fm.split("\n"):
            stripped = line.strip()
            if stripped.startswith("sources:"):
                in_sources = True
                continue
            if in_sources:
                if stripped.startswith("- "):
                    src = stripped[2:].strip().strip("'\"")
                    sources.add(src)
                elif stripped and not stripped.startswith("-"):
                    in_sources = False
    return sources


def diff_raw(raw_dir: Path, wiki_dir: Path) -> list[str]:
    """Return raw files not yet referenced by any wiki page.
    
    Compares raw/ files on disk against wiki page frontmatter sources.
    Returns relative paths (from project root) of unprocessed raw files.
    """
    if not raw_dir.exists():
        return []

    project_root = raw_dir.resolve().parent
    wiki_sources = _collect_wiki_sources(wiki_dir)

    results: set[str] = set()

    for f in sorted(raw_dir.resolve().rglob("*.md")):
        rel = str(f.relative_to(project_root))
        if rel not in wiki_sources:
            results.add(rel)

    return sorted(results)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Detect raw files not yet referenced by wiki pages"
    )
    parser.add_argument("--raw-dir", default="data/raw", help="Path to raw/ directory")
    parser.add_argument("--wiki-dir", default="data/wiki", help="Path to wiki/ directory")
    args = parser.parse_args()

    changed = diff_raw(
        raw_dir=Path(args.raw_dir),
        wiki_dir=Path(args.wiki_dir),
    )

    if not changed:
        print("No new files to process.", file=sys.stderr)
        sys.exit(1)

    for path in changed:
        print(path)


if __name__ == "__main__":
    main()
