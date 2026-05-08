"""Shared helpers for wiki linting."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

BASEDIR = Path(__file__).resolve().parent.parent.parent.parent
WIKI_DIR = BASEDIR / "data" / "wiki"


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
                result[current_key] = [
                    i.strip().strip('"').strip("'") for i in items if i.strip()
                ]
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


def _parse_yaml_frontmatter(text: str) -> dict | None:
    """Parse raw-file frontmatter via PyYAML. Returns None on absent/invalid."""
    if not text.startswith("---"):
        return None
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None
    try:
        fm = yaml.safe_load(parts[1])
    except yaml.YAMLError:
        return None
    return fm if isinstance(fm, dict) else None


def collect_pages(
    wiki_dir: Path = None,
) -> tuple[dict[str, str], dict[str, list[Path]]]:
    """Return ``(pages, paths_by_stem)``: stem→content for one of the
    colliding files (Obsidian wikilinks resolve by stem alone, so the
    dict cannot hold both), and stem→every path sharing the stem so
    the lint pass can flag collisions the stem-keyed dict cannot
    represent."""
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


def _find_relative(stem: str, wiki_dir: Path = None) -> str:
    """Find relative path for a page stem."""
    wiki_dir = wiki_dir if wiki_dir is not None else WIKI_DIR
    for f in wiki_dir.rglob("*.md"):
        if f.stem == stem:
            return str(f.relative_to(wiki_dir))
    return stem
