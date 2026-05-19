"""Frontmatter R/W and page enumeration helpers for kb-wiki-review.

Frontmatter writes use targeted regex substitution rather than
yaml.dump to preserve formatting, comments, key order, and quoting
across edits.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from kb_mcp import REPO_ROOT
from kb_mcp.cli.wiki.validators import REVIEW_STATUS_TYPES

WIKI_DIR = REPO_ROOT / "data" / "wiki"
REJECTED_DIR = REPO_ROOT / "data" / "rejected"


class PageNotFound(Exception):
    """The given stem matches no page under wiki/."""


class StemCollision(Exception):
    """Multiple pages share the given stem."""


@dataclass
class Page:
    path: Path
    rel: Path  # relative to wiki_dir
    fm: dict

    @property
    def stem(self) -> str:
        return self.path.stem


def resolve_stem(wiki_dir: Path, stem: str) -> Path:
    """Find a unique <stem>.md under wiki_dir.

    Raises PageNotFound or StemCollision when ambiguous.
    """
    matches = [
        p for p in wiki_dir.rglob(f"{stem}.md")
        if p.name != "_index.md"
    ]
    if not matches:
        raise PageNotFound(f"no page with stem {stem!r} in wiki/")
    if len(matches) > 1:
        rels = sorted(str(p.relative_to(wiki_dir)) for p in matches)
        raise StemCollision(
            f"stem {stem!r} matches multiple files:\n  - "
            + "\n  - ".join(rels)
            + "\nPass an explicit relative path instead."
        )
    return matches[0]


def _split_frontmatter(text: str) -> tuple[str, str] | None:
    """Return (fm_block, body) or None if no frontmatter detected.

    fm_block does NOT include the surrounding '---' fences.
    """
    if not text.startswith("---\n") and not text.startswith("---\r\n"):
        return None
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None
    return parts[1], parts[2]


def get_frontmatter_field(path: Path, key: str) -> str | None:
    """Return the YAML-decoded value of a top-level frontmatter field."""
    text = path.read_text()
    parts = _split_frontmatter(text)
    if parts is None:
        return None
    fm_block, _ = parts
    try:
        fm = yaml.safe_load(fm_block) or {}
    except yaml.YAMLError:
        return None
    if not isinstance(fm, dict):
        return None
    val = fm.get(key)
    return None if val is None else str(val)


def set_frontmatter_field(path: Path, key: str, value: str) -> None:
    """Set a top-level field in frontmatter, preserving file formatting.

    If the field exists (matched as ``^key:``), its value is replaced.
    If absent, the line is appended to the frontmatter block.
    Unquoted scalar values only — use add_frontmatter_lines for complex types.
    """
    text = path.read_text()
    parts = _split_frontmatter(text)
    if parts is None:
        raise ValueError(f"{path}: missing or malformed frontmatter")
    fm_block, body = parts

    pattern = re.compile(rf"^{re.escape(key)}:.*$", re.MULTILINE)
    if pattern.search(fm_block):
        new_fm = pattern.sub(f"{key}: {value}", fm_block, count=1)
    else:
        new_fm = fm_block.rstrip("\n") + f"\n{key}: {value}\n"

    path.write_text(f"---{new_fm}---{body}")


def add_frontmatter_lines(path: Path, lines: list[str]) -> None:
    """Append raw YAML lines to the frontmatter block (e.g. with quoted values).

    Each line must already include the ``key: value`` form; no escaping is done.
    Used for adding fields like ``rejected_at: "2026-05-19T..."`` and lists.
    """
    text = path.read_text()
    parts = _split_frontmatter(text)
    if parts is None:
        raise ValueError(f"{path}: missing or malformed frontmatter")
    fm_block, body = parts
    appended = "\n".join(lines)
    new_fm = fm_block.rstrip("\n") + "\n" + appended + "\n"
    path.write_text(f"---{new_fm}---{body}")


def iter_pages(wiki_dir: Path) -> list[Page]:
    """Yield every in-scope page (REVIEW_STATUS_TYPES) under wiki_dir."""
    out: list[Page] = []
    for f in sorted(wiki_dir.rglob("*.md")):
        if f.name == "_index.md" or f.name == "INDEX.md":
            continue
        text = f.read_text()
        parts = _split_frontmatter(text)
        if parts is None:
            continue
        try:
            fm = yaml.safe_load(parts[0]) or {}
        except yaml.YAMLError:
            continue
        if not isinstance(fm, dict):
            continue
        if fm.get("type") not in REVIEW_STATUS_TYPES:
            continue
        out.append(Page(path=f, rel=f.relative_to(wiki_dir), fm=fm))
    return out
