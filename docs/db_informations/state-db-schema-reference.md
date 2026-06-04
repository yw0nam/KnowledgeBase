# KB State DB — Schema Reference

Updated: 2026-06-04

## 1. Synopsis

- **Purpose**: Let agents/skills **read** the canonical KnowledgeBase state directly. Postgres is the sole source of truth; `data/` is a generated human-readable export.
- **I/O**: `psql "$DATABASE_URL" -tAc "<SELECT …>"` → rows. Reads are unrestricted. Discover sources here, never by scanning `data/`.
- **Writes are NOT done here.** All writes go through the HTTP API (`kb-web`) so write-time lint runs. Never `INSERT`/`UPDATE`/`DELETE` directly — `raw_sources`, `page_revisions`, and `wiki_edits` have append-only triggers that abort.

Connect with `DATABASE_URL` (see `.env.example`):
`postgresql+psycopg://knowledgebase:knowledgebase@localhost:15432/knowledgebase`
(For raw `psql`, drop the `+psycopg`: `psql "postgresql://knowledgebase:knowledgebase@localhost:15432/knowledgebase"`.)

> **Timestamps are text, not `timestamptz`.** Every `*_at` column is a text column with a CHECK enforcing KST ISO shape `YYYY-MM-DDTHH:MM:SS+09:00` — **except `raw_sources.captured_at`**, which has no shape check and is stored in **UTC** (`…+00:00`) at ingest time. To find raw by KST day, range over the UTC equivalent (see recipes).

## 2. Core Logic

### Tables (overview)

| Table | Key columns | Notes |
|---|---|---|
| `pages` | `slug` (unique), `title`, `type`, `category`, `review_status`, `origin`, `body_md`, `frontmatter` (jsonb), `export_path` (unique), `created_at`, `updated_at` | Canonical wiki pages |
| `raw_sources` | `source_key` (unique), `source_type`, `source_url`, `title`, `content_md`, `frontmatter` (jsonb), `captured_at` (UTC) | Immutable raw inputs (append-only) |
| `page_sources` | `page_id`→pages, `raw_source_id`→raw_sources, `citation_path` | Page → source citations |
| `page_revisions` | `page_id`→pages, `revision_number`, `change_kind`, `frontmatter`, `changed_fields`, `source`, `note`, `created_at` | Live audit trail (append-only) |
| `handoffs` | `handoff_id` (unique), `task_slug`, `subject`, `role`, `handoff_seq`, `status`, `frontmatter`, `body_md`, `export_path` (unique) | Handoff documents |
| `operation_logs` | `log_date`, `category`, `body_md` | `data/log.md` rows |
| `cron_runs` | `job_name`, `target` (date), `status`, `exit_code`, `log_body`, `log_path`, `started_at`, `finished_at` | Per-run cron evidence |
| `metrics` | `report_date`, `report_type`, `session_count`, `token_total`, `cost_usd`, `tool_error_count`, `metrics_json` | One row per `(report_date, report_type)` |
| `dispatches` | `page_stem`, `external_board_id`/`external_task_id` (unique pair), `status`, `idempotency_key` | Kanban dispatch ledger |
| `exports` | `target`, `status`, `message`, `exported_at` | Markdown export audit |
| `wiki_edits` | `page_stem`, `field`, `old_value`/`new_value` (jsonb), `source`, `edited_at` | Console frontmatter-edit audit (append-only) |

### Vocabularies (DB-level CHECK constraints)

- `pages.type`: `entity`, `concept`, `decision`, `question`, `improvement`, `checklist`, `summary`
- `pages.review_status`: `not_processed` → `pending_for_approve` → `approved`; `rejected` (NULL allowed, e.g. for `summary`)
- `pages.origin`: `ingested`, `authored`, `imported`
- `page_revisions.change_kind`: `import`, `create`, `update`, `approve`, `reject`, `export`
- `page_revisions.source`: `migration`, `console`, `agent`, `system`, `cli`
- `dispatches.status`: `dispatched`, `in_progress`, `done`, `failed`, `cancelled`, `cancelling`
- `wiki_edits.field`: `review_status`, `type`, `category`, `tags`
- `wiki_edits.source`: `console`, `migration`

> **App-enforced (no DB CHECK):** `handoffs.status`/`role`, `operation_logs.category`, `cron_runs.status`, `exports.status`. Allowed values are owned by the API/lint and the relevant skills, not the database.

Review lifecycle: a page enters `not_processed`, is promoted to `pending_for_approve`, then `approved` or `rejected`. On reject/TTL-sweep the `export_path` moves `wiki/… → rejected/…`.

## 3. Usage — read recipes

```bash
psql_kb() { psql "${DATABASE_URL/+psycopg/}" -tAc "$1"; }

# Promotion queue (unprocessed) — used by wiki-approval
psql_kb "SELECT slug, type, created_at FROM pages
         WHERE review_status='not_processed' ORDER BY updated_at DESC;"

# Pending human approval
psql_kb "SELECT slug, type FROM pages WHERE review_status='pending_for_approve';"

# One page's body
psql_kb "SELECT body_md FROM pages WHERE slug='<slug>';"

# A target day's summary pages (slugs are date-prefixed) — used by memory/cron-wrapup
psql_kb "SELECT slug FROM pages WHERE type='summary' AND slug LIKE '2026-06-04-%';"

# Daily memory summaries within a date range (weekly rollup)
psql_kb "SELECT slug FROM pages WHERE type='summary' AND slug LIKE '%-memory'
         AND left(slug,10) BETWEEN '2026-06-01' AND '2026-06-07' ORDER BY slug;"

# Raw ingested on a KST day — captured_at is UTC, so range over the day
FROM=$(date -u -d "2026-06-04 00:00:00+09:00" +%FT%T)
TO=$(date -u -d "2026-06-04 00:00:00+09:00 +1 day" +%FT%T)
psql_kb "SELECT source_key, source_type, captured_at FROM raw_sources
         WHERE captured_at >= '$FROM' AND captured_at < '$TO' ORDER BY captured_at;"

# Ready handoffs (optionally by task) — used by memory/cron-wrapup
psql_kb "SELECT task_slug, handoff_id, status FROM handoffs
         WHERE status='ready' ORDER BY updated_at DESC;"

# Cron run outcomes for a date — used by cron-wrapup (when populated)
psql_kb "SELECT job_name, status, exit_code FROM cron_runs WHERE target='2026-06-04';"

# Usage metrics for a date — used by cron-wrapup (when populated)
psql_kb "SELECT report_type, session_count, token_total, cost_usd FROM metrics WHERE report_date='2026-06-04';"
```

## Appendix

### A. PatchNote

- 2026-06-04: Expanded to a full per-table reference (Appendix B), added the timestamp/timezone gotcha (`captured_at` is UTC, all other `*_at` are KST-checked), the `wiki_edits` enums, the app-enforced-enum note, and raw/date-range read recipes. Linked from the DB-touching skills.
- 2026-06-04: Created. Postgres became the sole source of truth (SQLite removed); reads are direct `psql` against the schema above, writes stay gated through the API.

### B. Full table reference

Authoritative as of 2026-06-04. Regenerate after a migration with `psql "$DATABASE_URL_RAW" -c '\d <table>'`. All `*_at` columns are KST-ISO text (`…+09:00`) unless noted.

**`pages`** — canonical wiki pages
| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | integer | no | identity PK |
| `slug` | text | no | unique |
| `title` | text | no | |
| `type` | text | no | CHECK (see vocab) |
| `category` | text | yes | |
| `review_status` | text | yes | CHECK (see vocab); NULL allowed |
| `origin` | text | no | default `ingested`; CHECK |
| `body_md` | text | no | |
| `frontmatter` | jsonb | no | |
| `export_path` | text | yes | unique |
| `created_at` / `updated_at` | text | no | KST-ISO CHECK |

Indexes: `(review_status, updated_at DESC)`, `(type, category)`, unique `slug`, unique `export_path`. Referenced by `page_revisions`, `page_sources` (ON DELETE CASCADE).

**`raw_sources`** — immutable raw inputs
| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | integer | no | identity PK |
| `source_key` | text | no | unique |
| `source_type` | text | no | |
| `source_url` | text | yes | |
| `title` | text | yes | |
| `content_md` | text | no | |
| `frontmatter` | jsonb | no | |
| `captured_at` | text | yes | **UTC** (`+00:00`); no shape CHECK |
| `created_at` | text | no | KST-ISO CHECK |

Indexes: `(source_type, captured_at DESC)`, unique `source_key`. **Append-only**: `BEFORE UPDATE`/`BEFORE DELETE` triggers abort.

**`page_sources`** — page → raw citations
| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | integer | no | identity PK |
| `page_id` | integer | no | FK→pages (CASCADE) |
| `raw_source_id` | integer | yes | FK→raw_sources (RESTRICT) |
| `citation_path` | text | no | |
| `created_at` | text | no | KST-ISO CHECK |

Unique `(page_id, citation_path)`. Indexes on `page_id`, `raw_source_id`.

**`page_revisions`** — live audit trail
| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | integer | no | identity PK |
| `page_id` | integer | no | FK→pages (CASCADE) |
| `revision_number` | integer | no | unique with `page_id` |
| `change_kind` | text | no | CHECK (see vocab) |
| `body_md` | text | no | |
| `frontmatter` | jsonb | no | |
| `changed_fields` | jsonb | yes | |
| `source` | text | no | default `migration`; CHECK |
| `note` | text | yes | |
| `created_at` | text | no | KST-ISO CHECK |

Index `(page_id, created_at DESC)`. **Append-only** triggers.

**`handoffs`** — handoff documents
| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | integer | no | sequence PK |
| `handoff_id` | text | no | unique |
| `task_slug` | text | no | folder name, e.g. `wiki-daily-build` |
| `subject` | text | yes | |
| `role` | text | no | app-enforced |
| `handoff_seq` | integer | no | |
| `status` | text | no | app-enforced (e.g. `ready`, `consumed`) |
| `frontmatter` | json | no | |
| `body_md` | text | no | |
| `export_path` | text | no | unique |
| `created_at` / `updated_at` | text | no | KST-ISO CHECK |

Index `(task_slug, status)`. No DB CHECK constraints.

**`operation_logs`** — `data/log.md` rows
| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | integer | no | sequence PK |
| `log_date` | text | no | |
| `category` | text | no | app-enforced |
| `body_md` | text | no | |
| `created_at` | text | no | KST-ISO CHECK |

Index `(log_date, id)`.

**`cron_runs`** — per-run cron evidence
| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | integer | no | sequence PK |
| `job_name` | text | no | |
| `target` | text | no | date string |
| `status` | text | no | app-enforced |
| `exit_code` | integer | yes | |
| `log_body` | text | no | full log captured at submit |
| `log_path` | text | yes | |
| `started_at` / `finished_at` | text | yes | KST-ISO when present |
| `created_at` | text | no | KST-ISO CHECK |

Index `(target, job_name)`. Submitted via `POST /api/cron-runs` after each wrapper exits.

**`metrics`** — usage report metrics
| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | integer | no | sequence PK |
| `report_date` | text | no | unique with `report_type` |
| `report_type` | text | no | e.g. `opencode`, `claude-code`, `hermes` |
| `session_count` | integer | yes | |
| `token_total` | integer | yes | |
| `cost_usd` | double precision | yes | |
| `tool_error_count` | integer | yes | |
| `metrics_json` | json | no | full payload |
| `created_at` | text | no | |

Unique `(report_date, report_type)`.

**`dispatches`** — kanban dispatch ledger
| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | integer | no | identity PK |
| `page_stem` | text | no | |
| `page_path_at_dispatch` | text | no | |
| `external_board_id` / `external_task_id` | text | no | unique pair |
| `direction` | text | yes | |
| `status` | text | no | default `dispatched`; CHECK (see vocab) |
| `idempotency_key` | text | yes | partial-unique when not null |
| `created_at` / `dispatched_at` | text | no | KST-ISO CHECK |
| `last_status_at` | text | yes | KST-ISO CHECK when present |
| `result_payload` | jsonb | yes | |

Indexes `(page_stem, dispatched_at DESC)`, `(status, dispatched_at DESC)`.

**`exports`** — markdown export audit
| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | integer | no | sequence PK |
| `target` | text | no | |
| `status` | text | no | app-enforced |
| `message` | text | yes | |
| `exported_at` | text | no | |

Index `(exported_at)`.

**`wiki_edits`** — console frontmatter-edit audit
| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | integer | no | identity PK |
| `page_stem` | text | no | |
| `field` | text | no | CHECK (see vocab) |
| `old_value` / `new_value` | jsonb | yes | |
| `source` | text | no | default `console`; CHECK |
| `edited_at` | text | no | KST-ISO CHECK |

Index `(page_stem, edited_at DESC)`, partial index on `review_status` transitions. **Append-only** triggers.
