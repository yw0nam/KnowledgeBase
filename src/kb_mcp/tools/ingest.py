"""MCP tool: kb_ingest — run scripts/ingest-github.sh for given repos."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from ..core.ingest import DEFAULT_SCRIPT_PATH as _CORE_DEFAULT
from ..core.ingest import ingest_github as _ingest_github


DEFAULT_SCRIPT_PATH: Path = _CORE_DEFAULT


RepoStr = Annotated[
    str,
    StringConstraints(pattern=r"^[\w.-]+/[\w.-]+$", strip_whitespace=True),
]


class IngestInput(BaseModel):
    """Input for kb_ingest tool."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    repos: list[RepoStr] = Field(
        ...,
        description="GitHub repos to ingest, each in 'owner/repo' format.",
        min_length=1,
        max_length=20,
    )


async def kb_ingest(params: IngestInput) -> str:
    """Ingest CLAUDE.md + recent issues/PRs from the given GitHub repos.

    Writes files under raw/github/. Returns a JSON summary with
    returncode, stdout tail, stderr tail, and the list of repos processed.
    """
    result = _ingest_github(
        repos=params.repos,
        script_path=DEFAULT_SCRIPT_PATH,
    )
    ok = result["returncode"] == 0
    summary = {
        "status": "success" if ok else "error",
        "returncode": result["returncode"],
        "repos": result["repos"],
        "stdout": result["stdout"][-2000:],
        "stderr": result["stderr"][-2000:],
    }
    return json.dumps(summary, ensure_ascii=False, indent=2)


def register(mcp) -> None:
    mcp.tool(
        name="kb_ingest",
        annotations={
            "title": "Ingest GitHub Repos into KnowledgeBase",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )(kb_ingest)
