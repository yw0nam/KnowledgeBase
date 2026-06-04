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

Auto-reject stale unprocessed wiki pages via DB API.

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

### kb-web

FastAPI DB-canonical API server with Bearer auth.

```bash
kb-web [--reload] [--host HOST] [--port PORT]
```

Environment variables:

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | | Postgres URL (**required**) — also needed by host `kb-lint`, `alembic`, and `psql` reads |
| `KB_DATA_DIR` | `<repo>/data` | Markdown export tree (not the canonical store) |
| `KB_WEB_HOST` | `127.0.0.1` | Bind address |
| `KB_WEB_PORT` | `8765` | Listen port |
| `KB_API_TOKEN` | | Bearer auth token (required for write endpoints) |

Postgres is the sole source of truth. **Reads** go directly to the DB
(`psql "$DATABASE_URL" -c "…"`); see
[state DB schema reference](../db_informations/state-db-schema-reference.md).
**Writes** go through the API endpoints below. Copy `.env.example` → `.env` to
set `DATABASE_URL` for host-run tools.

### API Endpoints (write)

All write endpoints require `Authorization: Bearer $KB_API_TOKEN`.

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/pages` | Create or replace a wiki page (upsert by slug; re-runs append an `update` revision) |
| `PATCH` | `/api/pages/{slug}` | Partial update of a wiki page |
| `POST` | `/api/pages/{slug}/promote` | not_processed → pending_for_approve |
| `POST` | `/api/pages/{slug}/approve` | pending_for_approve → approved |
| `POST` | `/api/pages/{slug}/reject` | Reject wiki page |
| `POST` | `/api/pages/ttl-sweep` | Auto-reject stale unprocessed pages |
| `POST` | `/api/raw-sources` | Create raw source |
| `POST` | `/api/handoffs` | Create handoff document |
| `POST` | `/api/operation-logs` | Create operation log |
| `POST` | `/api/cron-runs` | Create cron run record |
| `POST` | `/api/metrics` | Upsert a metrics record (one per `report_date` + `report_type`) |
| `POST` | `/api/export/markdown` | Export all Markdown from DB |

Swagger UI at `/api/docs`.

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

- 2026-06-04: Postgres is the sole source of truth (SQLite removed). `DATABASE_URL` is required; reads use `psql` (see schema reference), writes use the API.
- 2026-06-04: `POST /api/pages` and `POST /api/metrics` are now idempotent upserts (re-runs/backfills replace in place rather than 409 or duplicate); `kb-lint --strict` now actually fails on warnings.
- 2026-06-04: DB-canonical rewrite — replaced kb-lint-wiki/kb-lint-handoff/kb-wiki-index/kb-wiki-review with kb-lint/kb-db-ttl-sweep/kb-submit-cron-run + daily report CLIs + kb-web + API endpoint reference.
- 2026-05-20: Added `kb-web` command and `dev-web.sh` for the local FastAPI + Vite review console.
- 2026-05-19: Added `kb-wiki-review` CLI (5 subcommands) for `review_status` lifecycle.
- 2026-05-18: Added kb-wiki-index, removed kb-mcp.
