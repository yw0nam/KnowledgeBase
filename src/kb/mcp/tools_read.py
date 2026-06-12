"""MCP read tools — read-only SQL surface over the KnowledgeBase Postgres store.

Two tools:

* ``query_sql`` — run a SELECT/WITH query and return rows. **Strictly read-only.**
* ``get_schema`` — introspect the ORM metadata; no DB connection needed.

Read-only enforcement (defense in depth, three layers):

1. **Statement guard** — cheap pre-check rejecting multi-statement input and any
   body that does not start with ``select`` / ``with``.
2. **Read-only transaction** — the real control. ``SET TRANSACTION READ ONLY`` is
   issued as the first statement of the autobegun transaction, so Postgres itself
   rejects any write (including data-modifying CTEs that slip past the prefix guard).
3. **Row cap** — ``fetchmany(limit)`` bounds the result regardless of the query.

Hardening note: a dedicated read-only DB role (GRANT SELECT only) is the strongest
control and is documented as the recommended deployment posture, but it is *not*
enforced here — the read-only transaction is the in-process control.
"""

from __future__ import annotations

from typing import Any

from fastmcp import Context
from sqlalchemy import text

from kb.db.models import Base
from kb.mcp._session import tool_session
from kb.mcp.server import mcp
from kb.mcp.validators import require

_JSON_SAFE = (str, int, float, bool, type(None), list, dict)


def _coerce(value: Any) -> Any:
    """Coerce a non-JSON-serializable value (datetime, Decimal, ...) to a string."""
    if isinstance(value, _JSON_SAFE):
        return value
    return str(value)


@mcp.tool
def query_sql(ctx: Context, sql: str | None = None, limit: int = 100) -> dict:
    """Run a READ-ONLY SQL query (SELECT / WITH only) against the KnowledgeBase DB.

    Use this to inspect the canonical Postgres store: pages, raw_sources,
    handoffs, operation_logs, cron_runs, metrics, etc. Call ``get_schema`` first
    to learn the tables and columns.

    Rules:
    * Only ``SELECT`` and ``WITH`` queries are allowed. A single trailing ``;`` is
      stripped; multiple statements are rejected.
    * The query runs inside a read-only Postgres transaction, so any write
      (INSERT/UPDATE/DELETE/DDL, including data-modifying CTEs) is rejected by the
      database and returned as an error — never executed.
    * At most ``limit`` rows are returned (default 100). ``truncated`` is True when
      the result hit the cap and more rows may exist.

    To change data, use the dedicated write tools (upsert_page, create_raw_source,
    …) which run lint → DB → Markdown export. SQL writes are intentionally
    impossible here because they would bypass that invariant.

    A dedicated read-only DB role is the recommended hardening for production and
    is documented, but the read-only transaction above is the enforced control.

    Returns ``{"rows": [...], "row_count": int, "columns": [...], "truncated": bool}``
    on success, or ``{"error": str, "code": str, "detail": None}`` on rejection.
    """
    missing = require(sql=sql)
    if missing:
        return missing

    # ── Layer 1: statement guard (cheap pre-check) ──────────────────────────
    body = sql.strip()
    if body.endswith(";"):
        body = body[:-1].rstrip()
    if ";" in body:
        return {
            "error": (
                "다중 문장(;)은 허용되지 않습니다. 단일 SELECT/WITH 쿼리만 실행하세요."
            ),
            "code": "read_only_violation",
            "detail": None,
        }
    head = body[:6].lower()
    if not (head.startswith("select") or head.startswith("with")):
        return {
            "error": (
                "읽기 전용 쿼리만 허용됩니다: SELECT 또는 WITH 로 시작해야 합니다."
            ),
            "code": "read_only_violation",
            "detail": None,
        }

    # ── Layers 2 & 3: read-only transaction + row cap ───────────────────────
    try:
        with tool_session(ctx) as (session, _):
            # Must be the first statement so it applies to the autobegun TX.
            session.execute(text("SET TRANSACTION READ ONLY"))
            result = session.execute(text(body))
            rows = result.fetchmany(limit)
            columns = list(result.keys())
            session.rollback()
    except Exception as exc:  # noqa: BLE001 — surface DB errors as a dict
        return {"error": str(exc), "code": "query_error", "detail": None}

    out_rows = [{col: _coerce(val) for col, val in zip(columns, row)} for row in rows]
    return {
        "rows": out_rows,
        "row_count": len(out_rows),
        "columns": columns,
        # Heuristic: if we got exactly `limit` rows, more may exist.
        "truncated": len(out_rows) == limit,
    }


@mcp.tool
def get_schema(ctx: Context) -> dict:
    """Return the KnowledgeBase DB schema (tables + columns) and example queries.

    Call this before ``query_sql`` to learn which tables and columns exist. The
    schema is read from the static ORM metadata, so no DB connection is needed.

    Returns ``{"tables": {<name>: {"columns": [{"name","type","nullable",
    "primary_key"}, ...]}}, "examples": [<sql>, ...]}``.
    """
    tables: dict[str, Any] = {}
    for name, table in Base.metadata.tables.items():
        tables[name] = {
            "columns": [
                {
                    "name": col.name,
                    "type": str(col.type),
                    "nullable": col.nullable,
                    "primary_key": col.primary_key,
                }
                for col in table.columns
            ]
        }
    return {
        "tables": tables,
        "examples": [
            "SELECT slug, type, review_status FROM pages "
            "WHERE review_status='pending_for_approve';",
            "SELECT source_key, source_type, captured_at FROM raw_sources "
            "ORDER BY created_at DESC LIMIT 20;",
            "SELECT handoff_id, task_slug, status FROM handoffs "
            "ORDER BY created_at DESC LIMIT 20;",
        ],
    }
