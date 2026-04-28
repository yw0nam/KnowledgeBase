"""
graph_query.py — thin CLI over kb_mcp.core.graph.search

Usage:
  python3 scripts/graph_query.py "TTS 관련 PR" [--dfs] [--budget 2000] [--graph data/graphify-out/graph.json]
"""
from __future__ import annotations

import argparse
import sys

from kb_mcp.core.graph import search


def main() -> None:
    parser = argparse.ArgumentParser(description="Query graphify knowledge graph")
    parser.add_argument("question", help="Query question")
    parser.add_argument("--dfs", action="store_true", help="Use DFS instead of BFS")
    parser.add_argument("--budget", type=int, default=2000, help="Token budget (default: 2000)")
    parser.add_argument(
        "--graph",
        default="data/graphify-out/graph.json",
        help="Path to graph.json",
    )
    args = parser.parse_args()

    try:
        out = search(
            question=args.question,
            mode="dfs" if args.dfs else "bfs",
            budget=args.budget,
            graph_path=args.graph,
        )
    except FileNotFoundError as e:
        print(f"ERROR: {e}. Run /kb_init first.", file=sys.stderr)
        sys.exit(1)

    print(out)


if __name__ == "__main__":
    main()
