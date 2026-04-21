"""kb_mcp — MCP server exposing KnowledgeBase graph search + ingest.

Usage:
    kb-mcp                              # stdio (default)
    kb-mcp --transport stdio
    kb-mcp --transport http --port 8000
"""
from __future__ import annotations

import argparse

from fastmcp import FastMCP

from .tools import ingest as ingest_tool
from .tools import search as search_tool


def build_server() -> FastMCP:
    mcp = FastMCP("kb_mcp")
    search_tool.register(mcp)
    ingest_tool.register(mcp)
    return mcp


def main() -> None:
    parser = argparse.ArgumentParser(prog="kb-mcp", description=__doc__)
    parser.add_argument(
        "--transport",
        choices=["stdio", "http"],
        default="stdio",
        help="Transport: stdio (local) or http (streamable HTTP, remote).",
    )
    parser.add_argument(
        "--host", default="127.0.0.1", help="Host for http transport."
    )
    parser.add_argument(
        "--port", type=int, default=8000, help="Port for http transport."
    )
    args = parser.parse_args()

    mcp = build_server()

    if args.transport == "stdio":
        mcp.run(transport="stdio")
    else:
        mcp.run(transport="streamable-http", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
