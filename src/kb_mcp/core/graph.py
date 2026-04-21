"""Graph loading + BFS/DFS traversal for graphify knowledge graphs."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

import networkx as nx
from networkx.readwrite import json_graph


DEFAULT_GRAPH_PATH = Path("data/graphify-out/graph.json")


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


def find_start_nodes(G: nx.DiGraph, question: str, top_n: int = 3) -> list[str]:
    terms = _tokens(question)
    if not terms:
        return []
    scored: list[tuple[int, str]] = []
    for nid, ndata in G.nodes(data=True):
        label = ndata.get("label", "").lower()
        score = sum(1 for t in terms if t in label)
        if score > 0:
            scored.append((score, nid))
    scored.sort(reverse=True)
    return [nid for _, nid in scored[:top_n]]


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
    terms = _tokens(question)

    def relevance(nid: str) -> int:
        label = G.nodes[nid].get("label", "").lower()
        return sum(1 for t in terms if t in label)

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
) -> str:
    if mode not in ("bfs", "dfs"):
        raise ValueError(f"mode must be 'bfs' or 'dfs', got {mode!r}")

    path = Path(graph_path) if graph_path is not None else DEFAULT_GRAPH_PATH
    G = load_graph(path)

    start_nodes = find_start_nodes(G, question)
    if not start_nodes:
        return f"No matching nodes found for: {question}"

    if mode == "dfs":
        nodes, edges = dfs(G, start_nodes)
    else:
        nodes, edges = bfs(G, start_nodes)

    return format_output(G, question, mode, start_nodes, nodes, edges, budget)
