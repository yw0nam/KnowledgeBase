"""Session helper for MCP tools — yields (session, data_dir) from lifespan ctx.

Usage inside a tool:

    @mcp.tool
    def my_tool(ctx: Context, ...) -> ...:
        with tool_session(ctx) as (session, data_dir):
            ...
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Generator

from sqlalchemy.orm import Session


@contextmanager
def tool_session(ctx: object) -> Generator[tuple[Session, Path], None, None]:
    """Yield ``(session, data_dir)`` from the MCP lifespan context.

    ``ctx.lifespan_context`` is the dict yielded by ``server_lifespan``.
    fastmcp 3.x exposes it directly as ``Context.lifespan_context``
    (confirmed against fastmcp 3.4.2 — matches the conference_demo reference pattern).
    """
    lc: dict = ctx.lifespan_context  # type: ignore[attr-defined]
    factory = lc["session_factory"]
    data_dir: Path = lc["data_dir"]
    session: Session = factory()
    try:
        yield session, data_dir
    finally:
        session.close()
