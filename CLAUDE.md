# KnowledgeBase

Personal LLM wiki backed by handoff system. Raw sources go in, LLM writes wiki pages, lint validates.

## Overview

KnowledgeBase is a memory-workflow system (v0) that captures knowledge from multiple sources, organizes it into a structured wiki, and maintains operational records via handoff documents. The system separates code (outer repo) from operational data (nested `data/` repo).

## Repository Layout

```
KnowledgeBase/                    # Outer repo: code, lint, templates, docs
├── src/kb/                   # CLI tools + FastAPI web server
│   ├── cli/
│   │   ├── lint_wiki.py          # kb-lint-wiki command
│   │   ├── lint_handoff.py       # kb-lint-handoff command
│   │   └── wiki_index.py         # kb-wiki-index command (regen wiki/INDEX.md)
│   └── web/                      # FastAPI review console backend (kb-web)
│       ├── app.py                #   FastAPI app factory
│       ├── config.py             #   KB_DATA_DIR, port config
│       ├── main.py               #   kb-web entrypoint
│       └── routes/               #   /api/queue, /api/pages, /api/dashboard
├── src/CLAUDE.md                 # CLAUDE.md file for src/
├── frontend/                     # Vite + React + TypeScript review console SPA
│   ├── src/                      #   Pages (QueuePage, DashboardPage), components, API clients
│   └── ...
├── scripts/
│   ├── ingest-github.sh          # GitHub source collection
│   └── dev-web.sh                # Start FastAPI + Vite together
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

data/                             # Nested git repo: raw sources + wiki (local-only)
├── .git/
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

- Never modify files in `data/raw/`. They are immutable after creation. Use `kb-lint-wiki --check-immutability` to enforce: git-status must not show modifications, `captured_at` must be ≤ file mtime (60s tolerance), and required raw frontmatter fields (`source_url`, `type`, `captured_at`, `contributor`) are always validated.
- `data/wiki/` pages must always list their `sources:` in frontmatter.
- Keep `data/log.md` updated for `data/` repo operations only: raw ingest, wiki page creation/update, handoff creation/update, promotion/rejection, cron/report outputs, and data lint results.
- Keep outer repo changes in `CHANGELOG.md`: source code, scripts, docs, skills, templates, config, schemas, and workflow contract changes.
- Do not write outer repo implementation details to `data/log.md`; reference the data artefact or handoff only if the operation created one.
- Lint must pass (0 errors) before committing wiki changes.
- Handoff documents are stored in `data/handoffs/` and tracked via git.
- Use uv for package management

## Change Records

Use two separate records because this repository has two git histories:

- `CHANGELOG.md` is for the outer repo. Update it when a change affects maintainers/operators or changes runtime behavior, CLI behavior, cron wrappers, skills, docs contracts, schemas, templates, or setup instructions.
- `data/log.md` is for the nested local data repo. Update it when a run creates or changes `data/wiki/`, `data/handoffs/`, `data/ops/`, `data/rejected/`, or records lint/cron/report outcomes.
- If one task changes both layers, update both records with layer-appropriate details. `CHANGELOG.md` says what changed in the product/workflow; `data/log.md` says what data artefacts were created or updated.
- Do not duplicate full changelog entries into `data/log.md`.
- Do not commit the nested `data/` repo unless the user explicitly asks for a data commit. Cron jobs and memory/approval workflows normally create and manage data changes for later user review.
- Exception: the `kb-cron-wrapup` workflow is expected to commit its own nested `data/` repo outputs after successful lint. The separate global morning digest is read-only: it reads the committed cron-wrapup artefact and sends a report, but does not create, edit, or commit KB data. `kb-cron-wrapup` must not push from within its AI session and must never commit the outer repo.
- If outer-repo work produces or adjusts `data/` artefacts for verification, leave those `data/` changes uncommitted unless the user specifically asks to handle them.

## Privacy

`data/` is a nested git repository scoped to private storage. It is never pushed to the outer repo's remote. It may be pushed to a dedicated private remote scoped to `data/` only — see `docs/data-sync.md`.

- Outer `.gitignore` excludes `data/`
- `data/.git` is independent from outer repo
- All raw sources and wiki pages stay private
- Handoff documents (which may contain sensitive decisions) stay private
- AI sessions and cron-wrapup commits do not push; push is a user/setup action (or, in a future Phase 3, a shell wrapper running outside the AI session)

Never commit `data/` contents to the outer repository. Never set `data/`'s remote to the outer repo's URL or any public host.

## Skills

Project skills live under `.claude/skills/`, auto-load by description match, and are the source of truth for workflow behavior.

- `knowledgebase-initialize` — initialize `data/`, verify tooling, and propose cron jobs for approval.
- `wiki-approval` — promote, approve, reject, or TTL-sweep wiki pages through the `review_status` lifecycle; runtime contract for wiki-promote cron.
- `wiki-authoring` — create or update source-backed `data/wiki/` pages with valid schemas, paths, wikilinks, templates, and lint order.
- `usage-report-setup` — select and wire source-specific OpenCode/Hermes/Claude Code usage report jobs.
- `handoff-document` — write or update handoff documents under `data/handoffs/` with lintable frontmatter, filename grammar, and canonical body sections.
- `memory-report` — daily, weekly, or monthly memory workflow (period dispatch inside the skill). Imports `wiki-authoring` for page edits and `handoff-document` for run handoffs.
- `cron-wrapup` — nightly KB cron wrap-up. Aggregates the previous day's usage reports, memory page, wiki-promote/TTL outcomes, and per-run cron evidence from `data/raw/ops/cron/{YYYY}/{MM}/{date}_kb-*.log` into a single Slack-digest-stable `wiki/summaries/.../{date}-cron-wrapup.md` plus run handoff. Runtime contract for the 05:00 cron job.

## Documentation

- [Documentation Index](docs/README.md) — design/reference document map
- [Architecture](docs/architecture.md) — repository layout and memory layers
- [Frontmatter Conventions](docs/reference/frontmatter.md) — schema reference; `wiki-authoring` and `handoff-document` carry runtime rules
- [Wiki Categories](docs/reference/wiki-categories.md) — category reference; use `wiki-authoring` at runtime
- [Commands](docs/reference/commands.md) — kb-lint-wiki, kb-lint-handoff, kb-wiki-index

## Linting

Use lint for src code before commit
```bash
./scripts/lint.sh
```
