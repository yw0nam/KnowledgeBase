# API → MCP Refactor Design

Date: 2026-06-12
Status: Draft for review
Branch: `refactor+api2mcp`

## Problem

KnowledgeBase currently serves its DB-canonical write surface through a FastAPI
HTTP app (`kb-web`). The only consumers are AI agents (opencode, Claude Code) and
deterministic cron CLIs — no human uses the HTTP API. The HTTP layer adds a
network hop, a running-daemon dependency for cron jobs, and a surface shaped for
browsers rather than agents.

Goal: replace the FastAPI write surface with a single **MCP server** (FastMCP,
streamable-http) that exposes the same write operations as tools, plus read tools
so agents stop needing raw `psql`. Postgres stays the sole source of truth and
Markdown stays a generated export.

## Decisions (locked)

1. **Full FastAPI removal + shared service layer.** Route-handler logic is
   extracted into a pure Python service layer. Both the MCP server and the
   deterministic CLIs call it **in-process**. `kb/web/` is deleted.
2. **Read tools:** a read-only `query_sql` tool plus `get_schema`. No structured
   per-entity read tools. Reads via `psql` remain available.
3. **Single KB MCP server** (not domain-split).
4. **Transport:** streamable-http long-running daemon.
5. **Auth:** bind to `127.0.0.1`, no token. Bearer auth removed.
6. **Scope split:** this spec covers the code refactor + core reference docs.
   Skill rewrites (`wiki-authoring`, `wiki-approval`, `handoff-document`,
   `memory-report`) and opencode MCP registration are a **separate follow-on
   sub-project**, started after the MCP daemon is verified working.

## Invariant (must not break)

Every write goes through the service layer so the DB-canonical contract holds:
`lint → mutate → revision/source bookkeeping → commit → Markdown export`. A
free-form write path that bypasses lint/export is forbidden — this is why
`query_sql` is strictly read-only.

## Architecture

```
┌─ kb/mcp/        FastMCP daemon (streamable-http).
│                 write tools = thin service wrappers; read tools = query_sql, get_schema
├─ kb/cli/*       deterministic cron CLIs — call the service layer in-process (no HTTP)
└─ kb/service/    ★ single write path. session in → lint → mutate → export → result.
                  HTTP/MCP-agnostic. Depends on kb/db, kb/lint, kb/service/export.py
```

Key effect: deterministic cron jobs no longer require a running daemon. The
daemon exists only for AI-agent read/write.

## Service layer — `src/kb/service/`

Extracted 1:1 from `kb/web/routes/db_canonical.py`. Each function takes a
`Session` plus typed params; returns a result `dict` on success or raises
`ServiceError(code, detail)`. Modules respect the 600-line limit:

| Module | Contents |
|--------|----------|
| `errors.py` | `ServiceError` with `code` ∈ {`not_found`, `conflict`, `lint_failed`, `export_failed`} and a `detail` payload |
| `pages.py` | `upsert_page`, `patch_page`, `promote_page`, `approve_page`, `reject_page`, `ttl_sweep` |
| `sources.py` | `create_raw_source` |
| `handoffs.py` | `create_handoff` |
| `ops.py` | `create_operation_log`, `create_cron_run`, `upsert_metrics`, `export_markdown` |
| `_helpers.py` | `_append_revision`, `_refresh_page_sources`, `_diff_page_fields`, `_sync_frontmatter`, `commit_and_export`, `_first_heading`, `_next_revision_number` (moved from the route module) |
| `session.py` | `session_scope()` — config+engine-backed session context manager shared by CLIs and MCP |

`commit_and_export(session, data_dir, result)` generalizes the route's
`_commit_export_or_500`: commit, run `export_all`, on export failure call
`record_export_failure` and raise `ServiceError("export_failed", ...)`.

### Relocations (out of the deleted `kb/web/`)

- `kb/web/_time.py` → `kb/service/_time.py`
- `kb/web/export.py` → `kb/service/export.py`
- `kb/web/config.py` → `kb/config.py` — drop `cors_origins`; rename `KB_WEB_HOST`/
  `KB_WEB_PORT` → `KB_MCP_HOST`/`KB_MCP_PORT`; keep `data_dir` (from `KB_DATA_DIR`).

## MCP server — `src/kb/mcp/`

| Module | Contents |
|--------|----------|
| `server.py` | FastMCP instance; `lifespan` builds engine + session_factory + resolves `data_dir`, runs `alembic upgrade head` once on startup; `main()` with argparse `--transport` (default `streamable-http`, `stdio` allowed for local dev), `--host`/`--port` (default `127.0.0.1:8765`). Registers tool modules. |
| `validators.py` | `NullableStr`/`NullableInt`/`NullableBool`/`NullableList` + `require()`, ported from the conference_demo reference. |
| `tools_write.py` | Write tools (below). |
| `tools_read.py` | `query_sql`, `get_schema`. |
| `_session.py` | Helper to open a session from `ctx.lifespan_context` for each tool call. |

### Tool conventions (from the reference pattern)

- Tools return plain `dict`/`list`. On `ServiceError`, return
  `{"error": <message>, "code": <code>, "detail": <payload>}` rather than raising
  — keeps the agent loop alive.
- Soft-required args use `require(...)`: optional params validated in the tool
  body, returning a retryable error dict instead of a hard MCP ValidationError.

### Write tools (service 1:1)

`create_raw_source`, `upsert_page`, `patch_page`, `promote_page`,
`approve_page`, `reject_page`, `ttl_sweep_pages`, `create_handoff`,
`create_operation_log`, `create_cron_run`, `upsert_metrics`, `export_markdown`.

### Read tools

- **`query_sql(sql, limit=100)`** — read-only, enforced three ways:
  1. Run inside a transaction with `SET TRANSACTION READ ONLY`, then rollback —
     Postgres rejects any write at the engine level.
  2. Guard: stripped SQL must start (case-insensitive) with `SELECT` or `WITH`;
     reject multi-statement input (`;` separating statements).
  3. `fetchmany(limit)` caps returned rows regardless of the query.
  Returns `list[dict]`. (Hardening option, documented not built: a dedicated
  `SELECT`-only Postgres role.)
- **`get_schema()`** — introspect SQLAlchemy metadata; return tables, columns,
  types, and a few example queries so the agent can author correct `query_sql`.

### Auth

Bind `127.0.0.1`, no token. The bearer-token check (`kb/web/auth.py`) is removed.

## Consumer migration

| Consumer | Now | After |
|----------|-----|-------|
| hermes/opencode/claude_code daily reports | `submit_markdown_page`, `submit_metrics` (HTTP) | `session_scope()` + `service.pages.upsert_page` / `service.ops.upsert_metrics` |
| `scripts/ingest-daily-papers.py` | `submit_raw_source` (HTTP) | `service.sources.create_raw_source` in-process |
| `kb/cli/db_ttl_sweep.py` | `post_json /pages/ttl-sweep` | `service.pages.ttl_sweep` in-process |
| `scripts/cron/_db.sh` / `kb-submit-cron-run` | HTTP POST | `service.ops.create_cron_run` in-process |

The markdown→payload parsers in `db_api.py` (`markdown_page_payload`,
`raw_source_payload`, `_split_frontmatter`, `_first_heading`) are pure and
reused — relocate to `kb/cli/_payloads.py`. The HTTP client (`post_json`,
`api_base_url`, `api_token`, `DbApiError`, `submit_*`) and `db_api.py` itself are
deleted. `kb-submit-cron-run` becomes a thin CLI over `service.ops.create_cron_run`.

## Packaging & deploy

- `pyproject.toml`: remove `kb-web` script and `fastapi` + `uvicorn` deps; add
  `fastmcp>=3.2.4` and `kb-mcp = "kb.mcp.server:main"`. Deterministic CLI entry
  points unchanged.
- `docker-compose.yml`: replace the `api` service with an `mcp` service
  (`command: kb-mcp --transport streamable-http --host 0.0.0.0 --port 8765`),
  same Dockerfile/build, same env minus `KB_API_TOKEN`. Keep `db`.
- `Dockerfile`: update the default command/entrypoint to `kb-mcp`.

## Testing

- **Service layer** unit tests against a test Postgres: each function's happy
  path + lint failure + conflict + state-transition guards. Replaces coverage
  the routes implicitly provided.
- **MCP tools:** tools are plain callables — invoke in-process with a session and
  assert dict shape, including the `{"error", "code", "detail"}` path.
- **`query_sql` read-only enforcement:** assert INSERT/UPDATE/DROP are rejected,
  SELECT/WITH pass, and `limit` caps rows.
- **Lifespan smoke test:** start the lifespan, assert tools are listed and the
  session factory connects.

## Core docs (in scope)

- `CLAUDE.md`: "writes go through the API" → "writes go through the `kb-mcp`
  tools"; "reads via `psql`" → "reads via the `query_sql` MCP tool or `psql`".
  Update the cron execution-patterns section (deterministic CLIs are now
  in-process and do not depend on a running daemon).
- `docs/db_informations/*`, `docs/reference/commands.md`: replace `kb-web` /
  HTTP-API references with `kb-mcp`; document `query_sql` / `get_schema`.
- `CHANGELOG.md`: record the surface change.

## Out of scope (follow-on sub-project)

- Rewriting skills that currently instruct "submit through the DB API"
  (`wiki-authoring`, `wiki-approval`, `handoff-document`, `memory-report`,
  `cron-wrapup`) to call `kb-mcp` tools.
- Registering `kb-mcp` as an MCP server in the opencode/Claude Code runtime used
  by LLM cron jobs.
- Started only after the MCP daemon is verified working end-to-end.

## Risks

- **LLM cron jobs** (memory-*, wiki-promote, cron-wrapup) write via the skills'
  DB-API instructions today. Until the follow-on sub-project lands, they would
  break — sequencing matters: keep this refactor on its branch and land the
  skill migration before cutting cron over to the new surface.
- **`query_sql` safety** depends on the read-only transaction holding; the
  statement guard and row cap are defense-in-depth, not the primary control.
