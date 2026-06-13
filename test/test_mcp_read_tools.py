"""Tests for kb.mcp.tools_read — read-only SQL surface (query_sql + get_schema).

Safety-critical: query_sql MUST be strictly read-only. A write via SQL would
bypass the lint→export invariant, so these tests run against REAL Postgres
(no mocks) — the read-only enforcement is exactly what must be verified at the
DB level.

Tool invocation: FunctionTool.fn is the original Python function; call it
directly with a fake context whose lifespan_context mimics server_lifespan.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select

import kb.mcp.tools_read  # noqa: F401 — registers query_sql + get_schema
import kb.mcp.tools_write  # noqa: F401 — registers write tools (for upsert_page)
from kb.db import make_engine, make_session_factory
from kb.db.models import OperationLog, Page
from kb.mcp.server import mcp

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def tool_ctx(data_dir: Path):
    """Fake Context whose lifespan_context mimics the real server dict."""
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


_CONCEPT_FM = {
    "type": "concept",
    "review_status": "not_processed",
    "created": "2026-06-04",
    "updated": "2026-06-04",
    "sources": [],
    "tags": ["mcp-read-test"],
}


def _make_page(ctx, slug: str) -> None:
    """Create a lint-valid concept page via the upsert_page write tool."""
    upsert = _get_tool_fn("upsert_page")
    result = upsert(
        ctx,
        slug=slug,
        type="concept",
        body_md=f"\n# {slug}\n\nBody content for read-tool test.\n",
        frontmatter=dict(_CONCEPT_FM),
        export_path=f"wiki/concepts/{slug}.md",
    )
    assert result.get("export", {}).get("status") == "success", result


def _page_count() -> int:
    engine = make_engine()
    factory = make_session_factory(engine)
    session = factory()
    try:
        return session.execute(select(func.count()).select_from(Page)).scalar_one()
    finally:
        session.close()
        engine.dispose()


def _operation_log_count() -> int:
    engine = make_engine()
    factory = make_session_factory(engine)
    session = factory()
    try:
        return session.execute(
            select(func.count()).select_from(OperationLog)
        ).scalar_one()
    finally:
        session.close()
        engine.dispose()


# ---------------------------------------------------------------------------
# 1. SELECT works
# ---------------------------------------------------------------------------


def test_query_sql_select_literal(database_url: str, tool_ctx: SimpleNamespace) -> None:
    fn = _get_tool_fn("query_sql")
    result = fn(tool_ctx, sql="SELECT 1 AS one")
    assert result["rows"] == [{"one": 1}], result
    assert result["columns"] == ["one"], result
    assert result["row_count"] == 1, result


# ---------------------------------------------------------------------------
# 2. Reads real data
# ---------------------------------------------------------------------------


def test_query_sql_reads_real_data(
    database_url: str, tool_ctx: SimpleNamespace
) -> None:
    _make_page(tool_ctx, "read-real-data")
    fn = _get_tool_fn("query_sql")
    result = fn(tool_ctx, sql="SELECT slug FROM pages")
    slugs = [r["slug"] for r in result["rows"]]
    assert "read-real-data" in slugs, result


# ---------------------------------------------------------------------------
# 3. Prefix guard rejects writes
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO pages (slug) VALUES ('x')",
        "UPDATE pages SET slug = 'y'",
        "DELETE FROM pages",
        "DROP TABLE pages",
    ],
)
def test_query_sql_prefix_guard_rejects_writes(
    database_url: str, tool_ctx: SimpleNamespace, sql: str
) -> None:
    before = _page_count()
    _make_page(tool_ctx, "guard-sentinel")
    fn = _get_tool_fn("query_sql")
    result = fn(tool_ctx, sql=sql)
    assert result.get("code") == "read_only_violation", result
    # The sentinel page is the only change; the rejected write created nothing.
    assert _page_count() == before + 1


# ---------------------------------------------------------------------------
# 4. Multi-statement rejected
# ---------------------------------------------------------------------------


def test_query_sql_multi_statement_rejected(
    database_url: str, tool_ctx: SimpleNamespace
) -> None:
    fn = _get_tool_fn("query_sql")
    result = fn(tool_ctx, sql="SELECT 1; DROP TABLE pages")
    assert result.get("code") == "read_only_violation", result


# ---------------------------------------------------------------------------
# 5. Transaction-level guard (CRITICAL) — data-modifying CTE passes prefix guard
# ---------------------------------------------------------------------------


def test_query_sql_transaction_guard_blocks_writing_cte(
    database_url: str, tool_ctx: SimpleNamespace
) -> None:
    before = _operation_log_count()
    fn = _get_tool_fn("query_sql")
    sql = (
        "WITH x AS ("
        "INSERT INTO operation_logs (log_date, category, body_md, created_at) "
        "VALUES ('2026-06-12','x','y','2026-06-12T00:00:00+09:00') "
        "RETURNING id) SELECT id FROM x"
    )
    result = fn(tool_ctx, sql=sql)
    # Passes the prefix guard (starts with WITH) but blocked by the read-only TX.
    assert result.get("code") == "query_error", result
    assert "error" in result
    assert _operation_log_count() == before, "no row may be written"


# ---------------------------------------------------------------------------
# 6. Row cap
# ---------------------------------------------------------------------------


def test_query_sql_row_cap(database_url: str, tool_ctx: SimpleNamespace) -> None:
    _make_page(tool_ctx, "cap-a")
    _make_page(tool_ctx, "cap-b")
    _make_page(tool_ctx, "cap-c")
    fn = _get_tool_fn("query_sql")
    result = fn(tool_ctx, sql="SELECT slug FROM pages", limit=2)
    assert result["row_count"] == 2, result
    assert result["truncated"] is True, result


# ---------------------------------------------------------------------------
# 7. get_schema
# ---------------------------------------------------------------------------


def test_get_schema(database_url: str, tool_ctx: SimpleNamespace) -> None:
    fn = _get_tool_fn("get_schema")
    result = fn(tool_ctx)
    tables = result["tables"]
    for name in ("pages", "raw_sources", "handoffs", "metrics"):
        assert name in tables, f"{name} missing from schema: {list(tables)}"

    page_cols = tables["pages"]["columns"]
    by_name = {c["name"]: c for c in page_cols}
    assert "slug" in by_name, page_cols
    assert "primary_key" in by_name["slug"]
    assert "nullable" in by_name["slug"]

    assert isinstance(result["examples"], list)
    assert len(result["examples"]) > 0
