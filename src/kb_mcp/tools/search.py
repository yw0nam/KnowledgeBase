"""MCP tool: kb_search — graph traversal search over graphify-out/graph.json."""
from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ..core.graph import DEFAULT_GRAPH_PATH as _CORE_DEFAULT
from ..core.graph import search as _search


DEFAULT_GRAPH_PATH: Path = _CORE_DEFAULT


class SearchInput(BaseModel):
    """Input for kb_search tool."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    question: str = Field(
        ...,
        description="Natural-language query; tokens are matched against node labels.",
        min_length=1,
        max_length=500,
    )
    mode: Literal["bfs", "dfs"] = Field(
        default="bfs",
        description="Traversal strategy: 'bfs' (breadth) or 'dfs' (depth).",
    )
    budget: int = Field(
        default=2000,
        description="Approximate token budget for the formatted output.",
        ge=100,
        le=20000,
    )


async def kb_search(params: SearchInput) -> str:
    """Search the KnowledgeBase knowledge graph and return a traversal summary.

    Returns a plain-text listing of matched nodes and their relations,
    truncated to roughly `budget` tokens.
    """
    return _search(
        question=params.question,
        mode=params.mode,
        budget=params.budget,
        graph_path=DEFAULT_GRAPH_PATH,
    )


def register(mcp) -> None:
    mcp.tool(
        name="kb_search",
        annotations={
            "title": "Search KnowledgeBase Graph",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )(kb_search)
