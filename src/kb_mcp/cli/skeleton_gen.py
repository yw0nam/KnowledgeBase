#!/usr/bin/env python3
"""
Deterministic wiki entity-page skeleton from graph.json.

Generates the parts of a wiki entity page that can be built mechanically from
the knowledge graph, leaving only narrative content for the LLM:

- frontmatter (type, created, updated, sources, aliases, tags)
- ## Relationships  (from graph.json edges where source_file matches the raw file)

The LLM is responsible for filling in (and only these):

- the `# Title` line
- the `## Overview` body
- the `## Key Details` body

It MUST NOT modify the frontmatter or the Relationships section.

Usage:
    uv run python -m kb_mcp.cli.skeleton_gen \\
        <raw_rel_path> <graph_json_abs> <wiki_root_abs>

    raw_rel_path     path of the raw file, relative to project root (e.g. raw/github/issues/repo_42.md)
    graph_json_abs   absolute path to graphify-out/graph.json
    wiki_root_abs    absolute path to wiki

Exit codes:
    0  skeleton emitted (relationships may be empty if no graph match)
    1  bad arguments
    2  graph.json missing or unreadable (an empty-relationships skeleton is still emitted)
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path
from typing import TextIO


def generate_skeleton(
    raw_rel_path: str,
    graph_json_path: Path,
    wiki_root: Path,
    out: TextIO = sys.stdout,
) -> int:
    """Emit a markdown skeleton for one raw file. Returns 0 on full success,
    2 if graph.json is missing/unreadable (skeleton with empty relationships
    is still emitted so the pipeline can continue)."""
    edges_for_file: list[tuple[str, str]] = []
    rc = 0

    if not graph_json_path.exists():
        print(
            f"skeleton_gen: graph.json not found at {graph_json_path} — "
            "emitting skeleton without relationships",
            file=sys.stderr,
        )
        rc = 2
    else:
        try:
            graph = json.loads(graph_json_path.read_text(encoding="utf-8"))
            edges_for_file = _collect_relationships(graph, raw_rel_path)
        except (json.JSONDecodeError, OSError) as e:
            print(f"skeleton_gen: failed to read graph.json: {e}", file=sys.stderr)
            rc = 2

    rel_lines = _resolve_wikilinks(edges_for_file, wiki_root)
    out.write(_render(raw_rel_path, rel_lines))
    return rc


def _collect_relationships(graph: dict, raw_rel_path: str) -> list[tuple[str, str]]:
    nodes_by_id = {n["id"]: n for n in graph.get("nodes", [])}

    # Match nodes by source_file. Try exact relative path first, fall back to
    # basename (graph.json may store a different prefix).
    matching_ids = {
        nid for nid, n in nodes_by_id.items()
        if n.get("source_file") == raw_rel_path
    }
    if not matching_ids:
        target_basename = Path(raw_rel_path).name
        matching_ids = {
            nid for nid, n in nodes_by_id.items()
            if Path(n.get("source_file") or "").name == target_basename
        }

    if not matching_ids:
        return []

    # NetworkX node-link format uses "links". Older graphify versions used
    # "edges". Some emit both _src/_tgt and source/target — prefer the latter.
    edges = graph.get("links") or graph.get("edges") or []

    seen: set[tuple[str, str]] = set()
    out: list[tuple[str, str]] = []
    for e in edges:
        src = e.get("source") if e.get("source") is not None else e.get("_src")
        tgt = e.get("target") if e.get("target") is not None else e.get("_tgt")
        if src not in matching_ids:
            continue
        target_node = nodes_by_id.get(tgt)
        if not target_node:
            continue
        label = target_node.get("label") or str(tgt)
        relation = e.get("relation") or "related"
        key = (label, relation)
        if key in seen:
            continue
        seen.add(key)
        out.append(key)

    out.sort()  # stable, deterministic output
    return out


def _resolve_wikilinks(
    relationships: list[tuple[str, str]],
    wiki_root: Path,
) -> list[str]:
    # Lint rule: never link to non-existent pages — emit plain text fallback.
    if not relationships:
        return []

    page_index = _index_wiki_pages(wiki_root) if wiki_root.exists() else {}

    lines: list[str] = []
    for label, relation in relationships:
        page = page_index.get(_normalize_label(label))
        if page is not None:
            lines.append(f"- [[{page.stem}|{label}]] ({relation})")
        else:
            lines.append(f"- {label} ({relation})  <!-- no wiki page yet -->")
    return lines


def _index_wiki_pages(wiki_root: Path) -> dict[str, Path]:
    index: dict[str, Path] = {}
    for md in wiki_root.rglob("*.md"):
        if md.name.startswith("_"):  # _index.md and friends are not link targets
            continue
        index.setdefault(_normalize_label(md.stem), md)
    return index


def _normalize_label(s: str) -> str:
    return s.replace(" ", "").replace("_", "").replace("-", "").lower()


def _render(raw_rel_path: str, rel_lines: list[str]) -> str:
    today = date.today().isoformat()
    rels_block = (
        "\n".join(rel_lines)
        if rel_lines
        else "<!-- no related entities found in graph -->"
    )
    return (
        f"---\n"
        f"type: entity\n"
        f'created: "{today}"\n'
        f'updated: "{today}"\n'
        f"sources:\n"
        f"  - {raw_rel_path}\n"
        f"aliases: []\n"
        f"tags: []\n"
        f"---\n"
        f"\n"
        f"# <!-- LLM TODO: title -->\n"
        f"\n"
        f"## Overview\n"
        f"\n"
        f"<!-- LLM TODO: 1-2 paragraph summary from the raw source -->\n"
        f"\n"
        f"## Key Details\n"
        f"\n"
        f"<!-- LLM TODO: technical details, implementation, architecture -->\n"
        f"\n"
        f"## Relationships\n"
        f"\n"
        f"{rels_block}\n"
    )


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 3:
        print(
            "usage: python -m kb_mcp.cli.skeleton_gen "
            "<raw_rel_path> <graph_json_abs> <wiki_root_abs>",
            file=sys.stderr,
        )
        return 1
    return generate_skeleton(
        raw_rel_path=args[0],
        graph_json_path=Path(args[1]),
        wiki_root=Path(args[2]),
    )


if __name__ == "__main__":
    sys.exit(main())
