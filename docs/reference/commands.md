# Commands

Updated: 2026-06-04

## 1. Synopsis

- **Purpose**: KnowledgeBase CLI commands for DB-backed validation, daily usage reports, TTL sweep, and API server.
- **I/O**: Shell command → DB API transactions or lint reports (exit 0 = pass, non-zero = fail).
- **Runtime**: Workflow ordering lives in `.claude/skills/`; this document is command reference.

## 2. Core Logic

### kb-lint

DB-backed lint for wiki pages and handoff documents.

```bash
kb-lint          # Run wiki + handoff (default)
kb-lint wiki     # Wiki only
kb-lint handoff  # Handoff only
kb-lint --strict # Treat warnings as errors
```

### kb-db-ttl-sweep

Auto-reject stale unprocessed wiki pages via the `kb.service` layer (in-process).

```bash
kb-db-ttl-sweep           # Default 7-day window
kb-db-ttl-sweep --days 7
```

### kb-submit-cron-run

Submit a cron run log to the DB API.

```bash
kb-submit-cron-run --job-name <name> --target <date> --status {success,failed} \
  --log-file <path> [--exit-code N] [--log-path <path>]
```

### kb-opencode-daily-report

Deterministic OpenCode daily usage report generator.

```bash
kb-opencode-daily-report --date YYYY-MM-DD [--dry-run] [--lint]
```

### kb-hermes-daily-report

Deterministic Hermes daily usage report generator.

```bash
kb-hermes-daily-report --date YYYY-MM-DD [--dry-run] [--lint]
```

### kb-claude-code-daily-report

Deterministic Claude Code daily usage report generator.

```bash
kb-claude-code-daily-report --date YYYY-MM-DD [--dry-run] [--lint]
```

### kb-mcp

FastMCP DB-canonical server (streamable-http, binds `127.0.0.1:8765`, **no auth** — local only).

```bash
uv run kb-mcp --transport streamable-http [--host HOST] [--port PORT]
```

Environment variables:

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | | Postgres URL (**required**) — also needed by `kb-lint`, `alembic`, and `psql` reads |
| `KB_DATA_DIR` | `<repo>/data` | Markdown export tree (not the canonical store) |
| `KB_MCP_HOST` | `127.0.0.1` | Bind address |
| `KB_MCP_PORT` | `8765` | Listen port |

Postgres is the sole source of truth. **Reads** go via the `query_sql` / `get_schema` MCP tools
or directly to the DB (`psql "$DATABASE_URL" -c "…"`); see
[state DB schema reference](../db_informations/state-db-schema-reference.md).
**Writes** go through the MCP tool calls below (each runs lint → DB write → Markdown export).
Copy `.env.example` → `.env` to set `DATABASE_URL` for host-run tools.

### MCP Tools

Writes are also reachable in-process via the `kb.service` layer (used by the deterministic cron CLIs — no running server needed).

| Tool | Purpose |
|---|---|
| `create_raw_source` | Ingest a raw source (insert + Markdown export) |
| `upsert_page` | Create or update a wiki page (lint → DB → export) |
| `patch_page` | Partially update an existing wiki page |
| `promote_page` | Advance page: `not_processed` → `pending_for_approve` |
| `approve_page` | Approve page: `pending_for_approve` → `approved` |
| `reject_page` | Reject a wiki page (moves export path to `rejected/`) |
| `ttl_sweep_pages` | Auto-reject stale unprocessed pages older than N days |
| `create_handoff` | Create a handoff document (lint → DB → export) |
| `create_operation_log` | Insert an operation log entry and export to `data/log.md` |
| `create_cron_run` | Record a cron job execution |
| `upsert_metrics` | Insert or update a metrics record for `(report_date, report_type)` |
| `export_markdown` | Export all canonical DB rows to Markdown/JSON files |
| `query_sql` | Run a read-only SELECT/WITH query against Postgres (row-capped) |
| `get_schema` | Return table/column schema and example queries (no DB connection needed) |

## 3. Usage

Use this file to look up command names and flags. Use `.claude/skills/` for command ordering:

| Task | Skill |
|---|---|
| Write wiki pages | `.claude/skills/wiki-authoring/SKILL.md` |
| Review/promote pages | `.claude/skills/wiki-approval/SKILL.md` |
| Write handoffs | `.claude/skills/handoff-document/SKILL.md` |
| Run periodic memory | `.claude/skills/memory-report/SKILL.md` |

---

## Appendix

### A. PatchNote

- 2026-06-12: Replaced `kb-web` (FastAPI + Bearer auth + HTTP endpoints) with `kb-mcp` (FastMCP, streamable-http, 127.0.0.1:8765, no auth). Replaced HTTP endpoint table with MCP tool reference table. Updated env vars (removed `KB_WEB_HOST/PORT`/`KB_API_TOKEN`; added `KB_MCP_HOST/PORT`). Added note that deterministic cron CLIs use the `kb.service` layer in-process without a running server.
- 2026-06-04: Postgres is the sole source of truth (SQLite removed). `DATABASE_URL` is required; reads use `psql` (see schema reference), writes went through the API (replaced 2026-06-12 by `kb-mcp` tools).
- 2026-06-04: `POST /api/pages` and `POST /api/metrics` were idempotent upserts; `kb-lint --strict` now actually fails on warnings.
- 2026-06-04: DB-canonical rewrite — replaced kb-lint-wiki/kb-lint-handoff/kb-wiki-index/kb-wiki-review with kb-lint/kb-db-ttl-sweep/kb-submit-cron-run + daily report CLIs + kb-web + API endpoint reference.
- 2026-05-20: Added `kb-web` command and `dev-web.sh` for the local FastAPI + Vite review console — replaced 2026-06-12.
- 2026-05-19: Added `kb-wiki-review` CLI (5 subcommands) for `review_status` lifecycle.
- 2026-05-18: Added kb-wiki-index, removed kb-mcp.
