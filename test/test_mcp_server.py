"""Smoke tests for kb.mcp.server — lifespan wiring and mcp metadata."""

from __future__ import annotations

import asyncio
from pathlib import Path

from sqlalchemy import text

from kb.mcp.server import mcp, server_lifespan


def test_mcp_name() -> None:
    assert mcp.name == "KnowledgeBase"


def test_lifespan_yields_expected_keys(database_url: str, data_dir: Path) -> None:
    """Enter server_lifespan and verify session_factory + data_dir are wired."""

    async def _run() -> dict:
        async with server_lifespan(mcp) as ctx:
            return ctx

    result = asyncio.run(_run())

    assert "session_factory" in result
    assert "data_dir" in result
    assert result["data_dir"] == data_dir


def test_lifespan_session_factory_works(database_url: str, data_dir: Path) -> None:
    """session_factory from lifespan can open a session that executes SELECT 1."""

    async def _run():
        async with server_lifespan(mcp) as ctx:
            factory = ctx["session_factory"]
            session = factory()
            try:
                row = session.execute(text("SELECT 1")).scalar()
                return row
            finally:
                session.close()

    result = asyncio.run(_run())
    assert result == 1
