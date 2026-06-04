# KnowledgeBase

Personal LLM wiki backed by handoff system. Raw sources go in, LLM writes wiki pages, lint validates.

**DB-Canonical**: A **Postgres** database (the compose `db` service, reached via `DATABASE_URL`) is the Source of Truth. Markdown files under `data/` are generated exports, not the canonical state. Reads go directly to Postgres (`psql`); writes go through the API so lint runs. See `docs/db_informations/state-db-schema-reference.md`.

## Overview

KnowledgeBase is a memory-workflow system (v0) that captures knowledge from multiple sources, organizes it into a structured wiki, and maintains operational records via handoff documents. The system separates code (outer repo) from operational data (`data/` export).

## Repository Layout

```
KnowledgeBase/                    # Outer repo: code, lint, templates, docs
├── src/kb/                   # CLI tools + FastAPI web server
│   ├── cli/
│   │   ├── lint.py                   # kb-lint command (wiki + handoff validation)
│   │   ├── db_ttl_sweep.py           # kb-db-ttl-sweep command
│   │   ├── db_api.py                 # DB API client (shared lib)
│   │   ├── opencode_daily_report.py  # kb-opencode-daily-report command
│   │   ├── hermes_daily_report.py    # kb-hermes-daily-report command
│   │   └── claude_code_daily_report.py  # kb-claude-code-daily-report command
│   └── web/                      # FastAPI DB-canonical API server (kb-web)
│       ├── app.py                #   FastAPI app factory
│       ├── config.py             #   KB_DATA_DIR, port config
│       ├── main.py               #   kb-web entrypoint
│       ├── auth.py               #   Bearer token auth
│       ├── export.py             #   Markdown + JSON export from DB
│       └── routes/db_canonical.py  #   DB-canonical write endpoints
├── src/CLAUDE.md                 # CLAUDE.md file for src/

├── scripts/
│   ├── ingest-github.sh          # GitHub source collection
├── docs/raw/                # Raw source frontmatter templates
├── .claude/skills/               # Runtime workflow contracts + bundled templates
├── pyproject.toml
├── CLAUDE.md                     # This file
├── README.md
├── docs/
│   ├── CLAUDE.md                 # CLAUDE.md file for docs/
│   ├── README.md                 # Documentation index
│   ├── architecture.md           # Repository and memory layer map
│   ├── db_informations/          # DB schemas and monitoring guides
│   └── reference/                # Schemas, categories, commands
│       ├── commands.md           # Command reference
│       ├── frontmatter.md        # Frontmatter schemas
│       └── wiki-categories.md    # Wiki categories
└── .gitignore                    # Excludes data/

data/                             # Generated Markdown export tree (KB_DATA_DIR); canonical state is Postgres
├── raw/
│   ├── github/
│   │   ├── claude-md/            # CLAUDE.md files ({owner}_{repo}_CLAUDE.md)
│   │   └── issues/               # Issues + PRs ({repo}_{number}.md)
│   ├── conversations/            # Desktop Chatbot history ({YYYY-MM}/chat_{timestamp}.md)
│   ├── calendar/                 # Calendar events ({YYYY-MM}/event_{date}_{slug}.md)
│   ├── web/                      # Web clippings
│   └── manual/                   # Hand-dropped files
├── handoffs/                     # Handoff documents (task-based)
├── wiki/
│   ├── entities/                 # Named objects ({subject}/{YYYY-MM}/)
│   ├── concepts/                 # Abstract ideas (flat)
│   ├── decisions/                # Architecture Decision Records
│   ├── questions/                # Saved Q&A
│   ├── improvements/             # Open-ended improvements (NEW)
│   ├── checklists/               # Operational checklists (NEW)
│   └── summaries/                # Time/subject rollups (daily/weekly/monthly/migration)
└── log.md                        # Append-only operation record
```

## Important Rules

- Never modify files in `data/raw/`. They are immutable after creation. Use `kb-lint` to enforce (via DB API): git-status must not show modifications, `captured_at` must be ≤ file mtime (60s tolerance), and required raw frontmatter fields (`source_url`, `type`, `captured_at`, `contributor`) are always validated.
- `data/wiki/` pages must always list their `sources:` in frontmatter.
- Keep `data/log.md` updated for `data/` repo operations only: raw ingest, wiki page creation/update, handoff creation/update, promotion/rejection, cron/report outputs, and data lint results.
- Keep outer repo changes in `CHANGELOG.md`: source code, scripts, docs, skills, templates, config, schemas, and workflow contract changes.
- Do not write outer repo implementation details to `data/log.md`; reference the data artefact or handoff only if the operation created one.
- Use uv for package management

## Change Records

- `CHANGELOG.md` is for the outer repo. Update it when a change affects maintainers/operators or changes runtime behavior, CLI behavior, cron wrappers, skills, docs contracts, schemas, templates, or setup instructions.
- Do not write outer repo implementation details to `data/log.md`; reference the data artefact or handoff only if the operation created one.
- If outer-repo work produces or adjusts `data/` artefacts for verification, leave those `data/` changes uncommitted unless the user specifically asks to handle them.

## Privacy

`data/` is a generated Markdown export directory. The canonical store is Postgres (reached via `DATABASE_URL`). See `docs/db-canonical.md`.

- Outer `.gitignore` excludes `data/`
- All raw sources and wiki pages stay private
- Handoff documents (which may contain sensitive decisions) stay private

Never commit `data/` contents to the outer repository.

## Skills

Project skills live under `.claude/skills/`, auto-load by description match, and are the source of truth for workflow behavior.

- `knowledgebase-initialize` — bring up Postgres (compose `db`), run migrations, verify tooling, and propose cron jobs for approval.
- `wiki-approval` — promote, approve, reject, or TTL-sweep wiki pages through the `review_status` lifecycle; runtime contract for wiki-promote cron.
- `wiki-authoring` — create or update source-backed `data/wiki/` pages with valid schemas, paths, wikilinks, templates, and lint order.
- `usage-report-setup` — select and wire source-specific OpenCode/Hermes/Claude Code usage report jobs.
- `handoff-document` — write or update handoff documents under `data/handoffs/` with lintable frontmatter, filename grammar, and canonical body sections.
- `memory-report` — daily, weekly, or monthly memory workflow (period dispatch inside the skill). Imports `wiki-authoring` for page edits and `handoff-document` for run handoffs.
- `cron-wrapup` — nightly KB cron wrap-up. Aggregates the previous day's usage reports, memory page, wiki-promote/TTL outcomes, and per-run cron evidence from `data/raw/ops/cron/{YYYY}/{MM}/{date}_kb-*.log` into a single Slack-digest-stable `wiki/summaries/.../{date}-cron-wrapup.md` plus run handoff. Runtime contract for the 05:00 cron job.

## Cron Jobs

The cron job runs KB cron jobs directly. The script delegates LLM work to `opencode run` where reasoning is needed, or calls deterministic `uv run` CLIs for pure data plumbing.

### Execution patterns

| Pattern | Used by | Mechanism |
|---------|---------|-----------|
| **LLM-Driven** | memory-daily/weekly/monthly, wiki-promote, cron-wrapup | skill-driven + opencode run  `opencode run --model anthropic/claude-sonnet-4-6` |
| **Deterministic** (no LLM) | opencode/hermes/claude-code daily reports, wiki-ttl-sweep, ingest-papers | `uv run kb-*-daily-report --date --lint`, `uv run kb-db-ttl-sweep --days 7`, `uv run python scripts/ingest-daily-papers.py` |

### Pipeline schedule (KST)

```
00:30  kb-db-ttl-sweep            deterministic
03:10  kb-opencode-daily-report   deterministic
03:15  kb-hermes-daily-report     deterministic
03:20  kb-claude-code-daily-report deterministic
03:30  kb-memory-daily            LLM-Driven
04:00  kb-wiki-promote            LLM-Driven
04:15  kb-memory-weekly (Mon)     LLM-Driven
04:45  kb-memory-monthly (1st)    LLM-Driven
05:00  kb-cron-wrapup             LLM-Driven
10:05  kb-ingest-daily-papers     deterministic
```

`morning-slack-digest` (09:00, Hermes agent) reads the wrapup artefact and delivers to Slack — it is **not** a KB cron job and runs with the agent.

### Proxy scripts

Cron jobs reference short script names (e.g. `kb-memory-daily.sh`) that resolve to `~/.hermes/scripts/`. Each is a thin proxy that `cd`s to KB root and `exec`s the real script under `scripts/cron/`. When adding a new cron script, create both the real script and the `~/.hermes/scripts/` proxy.

### Runtime contracts

OpenCode-powered jobs load their behavior from `.claude/skills/<name>/SKILL.md`:
- memory-* → `memory-report` (+ `wiki-authoring`, `handoff-document`)
- wiki-promote → `wiki-approval` (+ `wiki-authoring` if fixes needed)
- cron-wrapup → `cron-wrapup` (+ `handoff-document`)

All run logs go to `data/raw/ops/cron/{YYYY}/{MM}/{date}_{job}.log`.

## Documentation

- [Documentation Index](docs/README.md) — design/reference document map
- [Architecture](docs/architecture.md) — repository layout and memory layers
- [Workflows](docs/workflows.md) — at-a-glance diagram map (nightly pipeline, review lifecycle); skills own the execution detail
- [Frontmatter Conventions](docs/reference/frontmatter.md) — schema reference; `wiki-authoring` and `handoff-document` carry runtime rules
- [Wiki Categories](docs/reference/wiki-categories.md) — category reference; use `wiki-authoring` at runtime
- [Commands](docs/reference/commands.md) — kb-lint, kb-db-ttl-sweep, kb-submit-cron-run, daily report CLIs, kb-web

## Linting

Use lint for src code before commit
```bash
./scripts/lint.sh
```
