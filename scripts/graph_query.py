"""
graph_query.py — BFS/DFS traversal over graphify-out/graph.json

Usage:
  python3 scripts/graph_query.py "TTS 관련 PR" [--dfs] [--budget 2000] [--graph data/graphify-out/graph.json]
"""

import sys
import json
import argparse
from pathlib import Path

try:
    import networkx as nx
    from networkx.readwrite import json_graph
except ImportError:
    print("ERROR: networkx not installed. Run: pip install networkx", file=sys.stderr)
    sys.exit(1)


def find_start_nodes(G, question, top_n=3):
    terms = [t.lower() for t in question.split() if len(t) > 1]
    scored = []
    for nid, ndata in G.nodes(data=True):
        label = ndata.get("label", "").lower()
        score = sum(1 for t in terms if t in label)
        if score > 0:
            scored.append((score, nid))
    scored.sort(reverse=True)
    return [nid for _, nid in scored[:top_n]]


def bfs(G, start_nodes, depth=3):
    subgraph_nodes = set(start_nodes)
    subgraph_edges = []
    frontier = set(start_nodes)
    for _ in range(depth):
        next_frontier = set()
        for n in frontier:
            for neighbor in G.neighbors(n):
                if neighbor not in subgraph_nodes:
                    next_frontier.add(neighbor)
                    subgraph_edges.append((n, neighbor))
        subgraph_nodes.update(next_frontier)
        frontier = next_frontier
    return subgraph_nodes, subgraph_edges


def dfs(G, start_nodes, max_depth=6):
    subgraph_nodes = set()
    subgraph_edges = []
    visited = set()
    stack = [(n, 0) for n in reversed(start_nodes)]
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


def format_output(G, question, mode, start_nodes, subgraph_nodes, subgraph_edges, budget):
    terms = [t.lower() for t in question.split() if len(t) > 1]

    def relevance(nid):
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


def main():
    parser = argparse.ArgumentParser(description="Query graphify knowledge graph")
    parser.add_argument("question", help="Query question")
    parser.add_argument("--dfs", action="store_true", help="Use DFS instead of BFS")
    parser.add_argument("--budget", type=int, default=2000, help="Token budget (default: 2000)")
    parser.add_argument(
        "--graph",
        default="data/graphify-out/graph.json",
        help="Path to graph.json (default: data/graphify-out/graph.json)",
    )
    args = parser.parse_args()

    graph_path = Path(args.graph)
    if not graph_path.exists():
        print(f"ERROR: No graph found at {graph_path}. Run /kb_init first.", file=sys.stderr)
        sys.exit(1)

    data = json.loads(graph_path.read_text())
    # networkx 2.x: node_link_graph(data, attrs={"link": "links", ...})
    # networkx 3.x: node_link_graph(data, edges="links")
    try:
        G = json_graph.node_link_graph(data, edges="links")
    except TypeError:
        G = json_graph.node_link_graph(data, attrs={"source": "source", "target": "target", "name": "id", "key": "key", "link": "links"})

    start_nodes = find_start_nodes(G, args.question)
    if not start_nodes:
        print(f"No matching nodes found for: {args.question}", file=sys.stderr)
        sys.exit(0)

    mode = "dfs" if args.dfs else "bfs"
    if args.dfs:
        subgraph_nodes, subgraph_edges = dfs(G, start_nodes)
    else:
        subgraph_nodes, subgraph_edges = bfs(G, start_nodes)

    print(format_output(G, args.question, mode, start_nodes, subgraph_nodes, subgraph_edges, args.budget))


if __name__ == "__main__":
    main()
