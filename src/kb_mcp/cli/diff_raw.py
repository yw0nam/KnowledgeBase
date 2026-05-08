#!/usr/bin/env python3
"""
diff_raw.py — detect new/modified raw files that need processing.

Compares raw/ files on disk against:
  1. graphify-out/manifest.json (graph extraction status)
  2. wiki/entities/ (whether a wiki page references the raw file)

Usage:
    uv run python -m kb_mcp.cli.diff_raw [--raw-dir raw] [--manifest graphify-out/manifest.json] [--wiki-dir wiki]

Output (one relative path per line):
    raw/github/nanobot_runtime/issue/42-some-title.md

Exit codes:
    0  new/modified files found (printed to stdout)
    1  no new files (nothing to process)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _load_manifest(manifest_path: Path) -> dict[str, float]:
    """Load manifest.json → {absolute_path: mtime}."""
    if not manifest_path.exists():
        return {}
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        return {str(k): float(v) for k, v in data.items()}
    except (json.JSONDecodeError, OSError):
        return {}


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


def diff_raw(
    raw_dir: Path,
    manifest_path: Path,
    wiki_dir: Path,
    mode: str = "all",
) -> list[str]:
    """Return list of raw file paths (relative to project root) needing processing.

    mode:
        "graph" — files not in manifest or modified since last extraction
        "wiki"  — files not referenced by any wiki page
        "all"   — union of both (default)
    """
    if not raw_dir.exists():
        return []

    project_root = raw_dir.resolve().parent
    manifest = _load_manifest(manifest_path)

    # Normalize manifest keys to relative paths
    manifest_rel: dict[str, float] = {}
    for abs_path, mtime in manifest.items():
        p = Path(abs_path)
        try:
            rel = str(p.relative_to(project_root))
        except ValueError:
            # Old absolute path from before restructure — try extracting after data/
            if "/data/" in abs_path:
                rel = abs_path.split("/data/", 1)[1]
            else:
                rel = abs_path
        manifest_rel[rel] = mtime

    wiki_sources = _collect_wiki_sources(wiki_dir) if mode in ("wiki", "all") else set()

    results: set[str] = set()

    for f in sorted(raw_dir.resolve().rglob("*.md")):
        rel = str(f.relative_to(project_root))

        if mode in ("graph", "all"):
            if rel not in manifest_rel:
                results.add(rel)
            else:
                current_mtime = f.stat().st_mtime
                if current_mtime > manifest_rel[rel]:
                    results.add(rel)

        if mode in ("wiki", "all"):
            if rel not in wiki_sources:
                results.add(rel)

    return sorted(results)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Detect new/modified raw files needing processing"
    )
    parser.add_argument("--raw-dir", default="raw", help="Path to raw/ directory")
    parser.add_argument(
        "--manifest",
        default="graphify-out/manifest.json",
        help="Path to graphify manifest",
    )
    parser.add_argument("--wiki-dir", default="wiki", help="Path to wiki/ directory")
    parser.add_argument(
        "--mode",
        choices=["all", "graph", "wiki"],
        default="all",
        help="Detection mode: graph (unextracted), wiki (no wiki page), all (union)",
    )
    args = parser.parse_args()

    changed = diff_raw(
        raw_dir=Path(args.raw_dir),
        manifest_path=Path(args.manifest),
        wiki_dir=Path(args.wiki_dir),
        mode=args.mode,
    )

    if not changed:
        print("No new files to process.", file=sys.stderr)
        sys.exit(1)

    for path in changed:
        print(path)


if __name__ == "__main__":
    main()
