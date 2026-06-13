"""Tests for kb.mcp.tools_write — MCP tool wrappers over the service layer.

Covers the 5 minimum scenarios required by Task 6:
1. upsert_page happy path → export success, file on disk, DB row.
2. upsert_page missing required arg (slug) → require() error dict, no DB touch.
3. ServiceError surfaces as a dict: approve_page on not_processed slug → conflict.
4. create_raw_source round-trip → row + file.
5. Smoke: all 12 expected tool names are registered on mcp.

Tool invocation: FunctionTool.fn is the original Python function; call it directly
with a fake context whose lifespan_context mimics the real server_lifespan dict.
Tool listing: `asyncio.run(mcp.list_tools())` returns Tool objects with `.name`.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import select

import kb.mcp.tools_write  # noqa: F401 — registers all write tools
from kb.db import make_engine, make_session_factory
from kb.db.models import Page, RawSource
from kb.mcp.server import mcp

# ---------------------------------------------------------------------------
# Expected tool names (must match exactly what tools_write registers)
# ---------------------------------------------------------------------------

EXPECTED_TOOL_NAMES = {
    "create_raw_source",
    "upsert_page",
    "patch_page",
    "promote_page",
    "approve_page",
    "reject_page",
    "ttl_sweep_pages",
    "create_handoff",
    "create_operation_log",
    "create_cron_run",
    "upsert_metrics",
    "export_markdown",
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def tool_ctx(data_dir: Path):
    """Fake Context whose lifespan_context mimics the real server dict.

    Yields the context and disposes the underlying engine on teardown.
    """
    engine = make_engine()
    factory = make_session_factory(engine)
    ctx = SimpleNamespace(
        lifespan_context={"session_factory": factory, "data_dir": data_dir}
    )
    yield ctx
    engine.dispose()


def _get_tool_fn(tool_name: str):
    """Retrieve the underlying Python function for a registered FunctionTool."""
    tools = asyncio.run(mcp.list_tools())
    for tool in tools:
        if tool.name == tool_name:
            return tool.fn
    raise KeyError(f"Tool {tool_name!r} not found in mcp registry")


# ---------------------------------------------------------------------------
# Shared page frontmatter (lint-valid concept page)
# ---------------------------------------------------------------------------

_CONCEPT_FM = {
    "type": "concept",
    "review_status": "not_processed",
    "created": "2026-06-04",
    "updated": "2026-06-04",
    "sources": [],
    "tags": ["mcp-test"],
}


# ---------------------------------------------------------------------------
# 1. upsert_page happy path
# ---------------------------------------------------------------------------


def test_upsert_page_happy_path(
    database_url: str, data_dir: Path, tool_ctx: SimpleNamespace
) -> None:
    """upsert_page tool returns export.status == 'success', row in DB, file on disk."""
    ctx = tool_ctx
    fn = _get_tool_fn("upsert_page")

    result = fn(
        ctx,
        slug="mcp-test-concept",
        type="concept",
        body_md="\n# MCP Test Concept\n\nBody content for MCP write tool test.\n",
        frontmatter=dict(_CONCEPT_FM),
        export_path="wiki/concepts/mcp-test-concept.md",
    )

    assert isinstance(result, dict), f"Expected dict, got {type(result)}: {result}"
    assert (
        result.get("export", {}).get("status") == "success"
    ), f"Unexpected result: {result}"

    exported = data_dir / "wiki/concepts/mcp-test-concept.md"
    assert exported.exists(), "Exported file should exist on disk"

    # Verify DB row via the session_factory from the same ctx
    engine = make_engine()
    factory = make_session_factory(engine)
    session = factory()
    try:
        page = session.execute(
            select(Page).where(Page.slug == "mcp-test-concept")
        ).scalar_one()
        assert page.slug == "mcp-test-concept"
    finally:
        session.close()
        engine.dispose()


# ---------------------------------------------------------------------------
# 2. upsert_page missing required arg → require() error dict
# ---------------------------------------------------------------------------


def test_upsert_page_missing_slug_returns_error(
    database_url: str, tool_ctx: SimpleNamespace
) -> None:
    """Omitting slug returns the require() error dict; DB is not touched."""
    ctx = tool_ctx
    fn = _get_tool_fn("upsert_page")

    result = fn(
        ctx,
        # slug intentionally omitted
        type="concept",
        body_md="\n# Body\n\nContent.\n",
        frontmatter=dict(_CONCEPT_FM),
        export_path="wiki/concepts/no-slug.md",
    )

    assert "error" in result, f"Expected error key, got: {result}"
    assert "slug" in result["error"], f"Error should mention 'slug': {result['error']}"

    # DB must be untouched
    engine = make_engine()
    factory = make_session_factory(engine)
    session = factory()
    try:
        count = session.execute(
            select(Page).where(Page.slug == "no-slug")
        ).scalar_one_or_none()
        assert count is None, "No page should have been written to DB"
    finally:
        session.close()
        engine.dispose()


# ---------------------------------------------------------------------------
# 3. ServiceError surfaces as a dict — approve_page on not_processed slug
# ---------------------------------------------------------------------------


def test_approve_page_on_not_processed_returns_conflict_dict(
    database_url: str, tool_ctx: SimpleNamespace
) -> None:
    """approve_page on a not_processed page → ServiceError → dict with code='conflict'."""
    # First, create the page using the upsert tool so it's in not_processed state
    ctx = tool_ctx
    upsert_fn = _get_tool_fn("upsert_page")
    upsert_fn(
        ctx,
        slug="approve-direct",
        type="concept",
        body_md="\n# Approve Direct\n\nCreated via tool to test conflict path.\n",
        frontmatter=dict(_CONCEPT_FM),
        export_path="wiki/concepts/approve-direct.md",
    )

    # Now try to approve directly (skipping promote) — must get conflict
    approve_fn = _get_tool_fn("approve_page")
    result = approve_fn(ctx, slug="approve-direct")

    assert "error" in result, f"Expected error key, got: {result}"
    assert result.get("code") == "conflict", f"Expected code='conflict', got: {result}"
    assert "detail" in result, f"Expected detail key, got: {result}"

    # Ensure no exception was raised — tool must return a dict, not raise


# ---------------------------------------------------------------------------
# 4. create_raw_source round-trip
# ---------------------------------------------------------------------------


def test_create_raw_source_round_trip(
    database_url: str, data_dir: Path, tool_ctx: SimpleNamespace
) -> None:
    """create_raw_source tool inserts a DB row, exports a file, and writes to disk."""
    ctx = tool_ctx
    fn = _get_tool_fn("create_raw_source")

    result = fn(
        ctx,
        source_key="test/raw/mcp-tool-test.md",
        source_type="manual",
        content_md="# MCP Tool Test\n\nRaw source content.\n",
        source_url=None,
        title="MCP Tool Test",
    )

    assert isinstance(result, dict), f"Expected dict, got: {result}"
    assert "error" not in result, f"Got unexpected error: {result}"

    # Verify the exported Markdown file was written to disk
    assert (
        data_dir / "test/raw/mcp-tool-test.md"
    ).exists(), "Exported raw source file should exist on disk"

    # Verify DB row
    engine = make_engine()
    factory = make_session_factory(engine)
    session = factory()
    try:
        row = session.execute(
            select(RawSource).where(RawSource.source_key == "test/raw/mcp-tool-test.md")
        ).scalar_one()
        assert row.source_type == "manual"
    finally:
        session.close()
        engine.dispose()


# ---------------------------------------------------------------------------
# 5. Smoke — all 12 expected tool names registered on mcp
# ---------------------------------------------------------------------------


def test_all_expected_tool_names_registered() -> None:
    """All 12 write tool names must be a subset of the mcp registry.

    Subset (not exact-set) so the assertion stays correct as later tasks add
    read tools (query_sql, get_schema) onto the same global ``mcp`` — pytest
    imports every test module, which registers those extra tools too.
    """
    tools = asyncio.run(mcp.list_tools())
    registered_names = {tool.name for tool in tools}

    missing = EXPECTED_TOOL_NAMES - registered_names
    assert not missing, f"Tools not registered: {missing}"
