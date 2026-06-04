# KB State DB — Schema Reference

Updated: 2026-06-04

## 1. Synopsis

- **Purpose**: Let agents/skills **read** the canonical KnowledgeBase state directly. Postgres is the sole source of truth.
- **I/O**: `psql "$DATABASE_URL" -tAc "<SELECT …>"` → rows. Reads are unrestricted.
- **Writes are NOT done here.** All writes go through the HTTP API (`kb-web`) so write-time lint runs. Never `INSERT`/`UPDATE`/`DELETE` directly — `raw_sources` and `page_revisions` have append-only triggers that abort.

Connect with `DATABASE_URL` (see `.env.example`):
`postgresql+psycopg://knowledgebase:knowledgebase@localhost:15432/knowledgebase`
(For raw `psql`, drop the `+psycopg`: `psql "postgresql://knowledgebase:knowledgebase@localhost:15432/knowledgebase"`.)

## 2. Core Logic

### Tables

| Table | Key columns | Notes |
|---|---|---|
| `pages` | `slug` (unique), `title`, `type`, `category`, `review_status`, `origin`, `body_md`, `frontmatter` (jsonb), `export_path`, `created_at`, `updated_at` | Canonical wiki pages |
| `raw_sources` | `source_key` (unique), `source_type`, `source_url`, `title`, `content_md`, `frontmatter`, `captured_at` | Immutable raw inputs (append-only) |
| `page_sources` | `page_id`, `raw_source_id`, `citation_path` | Page → source citations |
| `page_revisions` | `page_id`, `revision_number`, `change_kind`, `frontmatter`, `changed_fields`, `source`, `note`, `created_at` | Audit trail (append-only) |
| `handoffs` | `handoff_id` (unique), `task_slug`, `subject`, `role`, `handoff_seq`, `status`, `frontmatter`, `body_md`, `export_path` | Handoff documents |
| `operation_logs` | `log_date`, `category`, `body_md` | `data/log.md` rows |
| `cron_runs` | `job_name`, `target` (date), `status`, `exit_code`, `log_path`, `log_body` | Per-run cron evidence |
| `metrics` | `report_date`, `report_type`, `session_count`, `token_total`, `cost_usd`, `tool_error_count`, `metrics_json` | One row per `(report_date, report_type)` |
| `exports` | `target`, `status`, `message`, `exported_at` | Markdown export audit |
| `dispatches` | `page_stem`, `external_board_id/task_id`, `status` | Kanban dispatch ledger |

(`wiki_edits` exists for history only; `page_revisions` is the sole live audit table.)

### Vocabularies

- `pages.type`: `entity`, `concept`, `decision`, `question`, `improvement`, `checklist`, `summary`
- `pages.review_status`: `not_processed` → `pending_for_approve` → `approved`; `rejected` (NULL allowed for `summary`)
- `pages.origin`: `ingested`, `authored`, `imported`
- `page_revisions.change_kind`: `import`, `create`, `update`, `approve`, `reject`, `export`
- `page_revisions.source`: `migration`, `console`, `agent`, `system`, `cli`
- `dispatches.status`: `dispatched`, `in_progress`, `done`, `failed`, `cancelled`, `cancelling`

Review lifecycle: a page enters `not_processed`, is promoted to `pending_for_approve`, then `approved` or `rejected`. On reject/TTL-sweep the `export_path` moves `wiki/… → rejected/…`.

## 3. Usage — read recipes

```bash
psql_kb() { psql "${DATABASE_URL/+psycopg/}" -tAc "$1"; }

# Promotion queue (unprocessed) — used by wiki-approval
psql_kb "SELECT slug, type, created_at FROM pages
         WHERE review_status='not_processed' ORDER BY updated_at DESC;"

# Pending human approval
psql_kb "SELECT slug, type FROM pages WHERE review_status='pending_for_approve';"

# One page's frontmatter + body
psql_kb "SELECT body_md FROM pages WHERE slug='<slug>';"

# A date's summary pages
psql_kb "SELECT slug FROM pages WHERE type='summary' AND created_at LIKE '2026-06-04%';"

# Cron run outcomes for a date — used by cron-wrapup
psql_kb "SELECT job_name, status, exit_code FROM cron_runs WHERE target='2026-06-04';"

# Usage metrics for a date
psql_kb "SELECT report_type, token_total, cost_usd FROM metrics WHERE report_date='2026-06-04';"
```

## Appendix

### A. PatchNote

- 2026-06-04: Created. Postgres became the sole source of truth (SQLite removed); reads are direct `psql` against the schema above, writes stay gated through the API.
