"""KnowledgeBase FastMCP server.

DB-canonical write+read surface over the KnowledgeBase Postgres store.
Writes (pages, raw sources, handoffs, logs, metrics) run lint→DB→Markdown export.
Reads via query_sql (read-only SQL) and get_schema.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config as AlembicConfig
from fastmcp import FastMCP

from kb import REPO_ROOT, data_dir as resolve_data_dir
from kb.db import make_engine, make_session_factory

logger = logging.getLogger(__name__)


# ── Lifespan ──────────────────────────────────────────────────────────────────


@asynccontextmanager
async def server_lifespan(server: FastMCP) -> AsyncIterator[dict[str, Any]]:
    """Build DB engine, run migrations, resolve data_dir; yield context dict."""
    # Run Alembic migrations (idempotent — safe if already at head)
    cfg = AlembicConfig(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "alembic"))
    await asyncio.to_thread(command.upgrade, cfg, "head")
    logger.info("alembic upgrade head complete")

    engine = make_engine()
    session_factory = make_session_factory(engine)
    data_dir_path: Path = resolve_data_dir()

    logger.info("KnowledgeBase MCP server started (data_dir=%s)", data_dir_path)

    try:
        yield {
            "session_factory": session_factory,
            "data_dir": data_dir_path,
        }
    finally:
        engine.dispose()
        logger.info("KnowledgeBase MCP server shut down")


# ── FastMCP app ───────────────────────────────────────────────────────────────

mcp = FastMCP(
    name="KnowledgeBase",
    instructions=(
        "DB-canonical KnowledgeBase write+read server. "
        "Writes (pages, raw sources, handoffs, logs, metrics) run lint→DB→Markdown export. "
        "Reads via query_sql (read-only SQL) and get_schema."
    ),
    lifespan=server_lifespan,
)


# ── Tool registrations (added in later tasks) ─────────────────────────────────
# tools_read will be added in the next task (Task 7).


# ── Entrypoint ────────────────────────────────────────────────────────────────


def main() -> None:
    """Run the KnowledgeBase MCP server."""
    from kb.mcp import tools_write  # noqa: F401  (registers write tools)

    # tools_read will be imported here in the next task (Task 7)

    parser = argparse.ArgumentParser(description="KnowledgeBase MCP server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "streamable-http", "sse"],
        default="streamable-http",
        help="Transport protocol (default: streamable-http)",
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("KB_MCP_HOST", "127.0.0.1"),
        help="Bind host for HTTP transports (default: $KB_MCP_HOST or 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("KB_MCP_PORT", "8765")),
        help="Bind port for HTTP transports (default: $KB_MCP_PORT or 8765)",
    )
    args = parser.parse_args()

    kwargs: dict[str, Any] = {"transport": args.transport}
    if args.transport != "stdio":
        kwargs["host"] = args.host
        kwargs["port"] = args.port

    mcp.run(**kwargs)


if __name__ == "__main__":
    main()
