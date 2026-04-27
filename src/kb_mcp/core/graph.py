"""Graph loading + BFS/DFS traversal for graphify knowledge graphs."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Iterable

import networkx as nx
from networkx.readwrite import json_graph


DEFAULT_GRAPH_PATH = Path("data/graphify-out/graph.json")

_WIKILINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")


def load_graph(path: str | Path) -> nx.DiGraph:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"No graph found at {p}")
    data = json.loads(p.read_text())
    try:
        return json_graph.node_link_graph(data, edges="links")
    except TypeError:
        return json_graph.node_link_graph(
            data,
            attrs={
                "source": "source",
                "target": "target",
                "name": "id",
                "key": "key",
                "link": "links",
            },
        )


def _tokens(question: str) -> list[str]:
    return [t.lower() for t in question.split() if len(t) > 1]


def _is_cjk_char(ch: str) -> bool:
    # CJK Unified Ideographs (U+4E00-U+9FFF) plus Hangul syllables
    # (U+AC00-U+D7AF), since Korean queries are the common case here.
    return ("一" <= ch <= "鿿") or ("가" <= ch <= "힯")


def _has_cjk(s: str) -> bool:
    return any(_is_cjk_char(ch) for ch in s)


def _cjk_aware_match(target: str, query: str) -> bool:
    """True if target has a meaningful match in query.

    - If target contains CJK chars (CJK Ideographs U+4E00-U+9FFF or Hangul
      syllables U+AC00-U+D7AF), use 2-char sliding window bigram match (any
      2-char window from target containing a CJK char and present in
      query → match).
    - Otherwise (Latin/etc): any whitespace-split word from target with
      len > 2 present in query (case-insensitive).
    """
    if not target or not query:
        return False
    target_lower = target.lower()
    query_lower = query.lower()
    if _has_cjk(target):
        return any(
            target_lower[j : j + 2] in query_lower
            for j in range(len(target_lower) - 1)
            if any(_is_cjk_char(c) for c in target_lower[j : j + 2])
        )
    return any(
        word in query_lower
        for word in target_lower.split()
        if len(word) > 2
    )


def _collect_index_aliases(wiki_dir: Path) -> list[tuple[str, str]]:
    """Recursively read every `_index.md` under wiki_dir, extract wikilinks
    [[Stem]] or [[Stem|Display]], and return (surface_title, target_stem)
    pairs.

    surface_title is what we match against the query; target_stem is what
    we substring-match against graph node labels. For plain [[Stem]] both
    fields are equal. For [[Stem|Display]] we emit (Stem, Stem) and
    (Display, Stem) so a Korean alias still boosts the Latin-stem node.
    Empty list if wiki_dir doesn't exist. Files we can't read (bad encoding,
    permissions) are skipped with a stderr note.
    """
    if not wiki_dir.exists():
        return []
    pairs: list[tuple[str, str]] = []
    for f in wiki_dir.rglob("_index.md"):
        try:
            content = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            print(f"kb_search: skipping unreadable {f}: {e}", file=sys.stderr)
            continue
        for stem, display in _WIKILINK_RE.findall(content):
            stem = stem.strip()
            if not stem:
                continue
            pairs.append((stem, stem))
            if display:
                display = display.strip()
                if display:
                    pairs.append((display, stem))
    return pairs


def _collect_questions_aliases(wiki_dir: Path) -> list[tuple[str, str]]:
    """Read every *.md under wiki_dir/questions/, returning (surface_title,
    file_stem) pairs.

    Both the file stem and the first H1 (`# ...`) line of the file map back
    to the file stem, so a CJK H1 still boosts a Latin-stem-named graph
    node. Empty list if questions/ doesn't exist. Files we can't read (bad
    encoding, permissions) contribute their stem but no H1, with a stderr
    note.
    """
    questions_dir = wiki_dir / "questions"
    if not questions_dir.exists():
        return []
    pairs: list[tuple[str, str]] = []
    for f in questions_dir.glob("*.md"):
        stem = f.stem
        pairs.append((stem, stem))
        try:
            content = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            print(f"kb_search: skipping unreadable {f}: {e}", file=sys.stderr)
            continue
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("# ") and not stripped.startswith("## "):
                h1 = stripped[2:].strip()
                if h1:
                    pairs.append((h1, stem))
                break
    return pairs


def find_start_nodes(
    G: nx.DiGraph,
    question: str,
    *,
    wiki_dir: Path | None = None,
    top_n: int = 3,
) -> list[str]:
    if not question:
        return []

    scored: dict[str, int] = {}

    # 1. Score graph nodes by direct CJK-aware label match.
    for nid, ndata in G.nodes(data=True):
        label = ndata.get("label", "")
        if _cjk_aware_match(label, question):
            scored[nid] = scored.get(nid, 0) + 1

    # 2. Wiki-driven expansion: alias pairs from _index.md and questions/*.md.
    #    Each pair is (surface_title, target_stem). We match surface against
    #    the query but substring-test target_stem against node labels, so a
    #    CJK display alias can still boost a Latin-stem-named node.
    if wiki_dir is not None and wiki_dir.exists():
        pairs: list[tuple[str, str]] = []
        pairs.extend(_collect_index_aliases(wiki_dir))
        pairs.extend(_collect_questions_aliases(wiki_dir))
        matched_targets = {
            target for surface, target in pairs
            if _cjk_aware_match(surface, question)
        }
        if matched_targets:
            for nid, ndata in G.nodes(data=True):
                label_lower = ndata.get("label", "").lower()
                for target in matched_targets:
                    if target.lower() in label_lower:
                        scored[nid] = scored.get(nid, 0) + 5
                        break

    if not scored:
        return []

    ranked = sorted(scored.items(), key=lambda kv: kv[1], reverse=True)
    return [nid for nid, score in ranked[:top_n] if score > 0]


def bfs(
    G: nx.DiGraph, start_nodes: Iterable[str], depth: int = 3
) -> tuple[set[str], list[tuple[str, str]]]:
    subgraph_nodes: set[str] = set(start_nodes)
    subgraph_edges: list[tuple[str, str]] = []
    frontier: set[str] = set(subgraph_nodes)
    for _ in range(depth):
        next_frontier: set[str] = set()
        for n in frontier:
            for neighbor in G.neighbors(n):
                if neighbor not in subgraph_nodes:
                    next_frontier.add(neighbor)
                    subgraph_edges.append((n, neighbor))
        subgraph_nodes.update(next_frontier)
        frontier = next_frontier
    return subgraph_nodes, subgraph_edges


def dfs(
    G: nx.DiGraph, start_nodes: Iterable[str], max_depth: int = 6
) -> tuple[set[str], list[tuple[str, str]]]:
    subgraph_nodes: set[str] = set()
    subgraph_edges: list[tuple[str, str]] = []
    visited: set[str] = set()
    stack: list[tuple[str, int]] = [(n, 0) for n in reversed(list(start_nodes))]
    while stack:
        node, depth = stack.pop()
        if node in visited or depth > max_depth:
            continue
        visited.add(node)
        subgraph_nodes.add(node)
        for neighbor in G.neighbors(node):
            if neighbor not in visited:
                stack.append((neighbor, depth + 1))
                subgraph_edges.append((node, neighbor))
    return subgraph_nodes, subgraph_edges


def format_output(
    G: nx.DiGraph,
    question: str,
    mode: str,
    start_nodes: list[str],
    subgraph_nodes: set[str],
    subgraph_edges: list[tuple[str, str]],
    budget: int,
) -> str:
    def relevance(nid: str) -> int:
        label = G.nodes[nid].get("label", "")
        return 1 if _cjk_aware_match(label, question) else 0

    ranked_nodes = sorted(subgraph_nodes, key=relevance, reverse=True)
    start_labels = [G.nodes[n].get("label", n) for n in start_nodes]

    lines = [
        f"Traversal: {mode.upper()} | Start: {start_labels} | {len(subgraph_nodes)} nodes"
    ]
    for nid in ranked_nodes:
        d = G.nodes[nid]
        lines.append(
            f"  NODE {d.get('label', nid)}"
            f" [src={d.get('source_file', '')} loc={d.get('source_location', '')}]"
        )
    for u, v in subgraph_edges:
        if u in subgraph_nodes and v in subgraph_nodes:
            e = G.edges[u, v]
            lines.append(
                f"  EDGE {G.nodes[u].get('label', u)}"
                f" --{e.get('relation', '')} [{e.get('confidence', '')}]-->"
                f" {G.nodes[v].get('label', v)}"
            )

    output = "\n".join(lines)
    char_budget = budget * 4
    if len(output) > char_budget:
        output = output[:char_budget] + f"\n... (truncated at ~{budget} token budget)"
    return output


def search(
    question: str,
    mode: str = "bfs",
    budget: int = 2000,
    graph_path: str | Path | None = None,
    wiki_dir: str | Path | None = None,
) -> str:
    if mode not in ("bfs", "dfs"):
        raise ValueError(f"mode must be 'bfs' or 'dfs', got {mode!r}")

    path = Path(graph_path) if graph_path is not None else DEFAULT_GRAPH_PATH
    G = load_graph(path)

    if wiki_dir is None:
        derived = path.parent.parent / "wiki"
        wiki_path: Path | None = derived if derived.exists() else None
    else:
        wp = Path(wiki_dir)
        wiki_path = wp if wp.exists() else None

    start_nodes = find_start_nodes(G, question, wiki_dir=wiki_path)
    if not start_nodes:
        return f"No matching nodes found for: {question}"

    if mode == "dfs":
        nodes, edges = dfs(G, start_nodes)
    else:
        nodes, edges = bfs(G, start_nodes)

    return format_output(G, question, mode, start_nodes, nodes, edges, budget)
