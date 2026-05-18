# KnowledgeBase

Personal LLM wiki backed by handoff system. Raw sources go in, LLM writes wiki pages, lint validates.

## Overview

KnowledgeBase is a memory-workflow system (v0) that captures knowledge from multiple sources, organizes it into a structured wiki, and maintains operational records via handoff documents. The system separates code (outer repo) from operational data (nested `data/` repo).

## Repository Layout

```
KnowledgeBase/                    # Outer repo: code, lint, templates, docs
├── src/kb_mcp/                   # MCP server + CLI tools
│   ├── cli/
│   │   ├── ingest.py             # kb-mcp ingest command
│   │   ├── lint_wiki.py          # kb-lint-wiki command
│   │   └── lint_handoff.py       # kb-lint-handoff command
│   └── mcp_server.py
├── src/CLAUDE.md                 # CLAUDE.md file for src/
├── scripts/
│   └── ingest-github.sh          # GitHub source collection
├── templates/                    # Frontmatter + handoff templates
│   ├── wiki/                     #   Wiki page templates (entity, concept, decision, …)
│   │   └── summaries/            #     Summary subtypes (daily, weekly, …)
│   ├── handoff/                  #   Handoff templates (task, final, readme)
│   └── raw/                      #   Raw source frontmatter
├── pyproject.toml
├── CLAUDE.md                     # This file
├── README.md
├── docs/
│   ├── CLAUDE.md                 # CLAUDE.md file for docs/
│   ├── README.md                 # Documentation index
│   ├── architecture.md           # Repository and memory layer map
│   ├── workflows/                # Operating procedures
│   │   ├── cron-jobs.md          # Cron schedule, wrappers, and failure policy
│   │   ├── handoff-system.md     # Handoff system spec
│   │   ├── periodic-memory-workflow.md # Daily/weekly/monthly memory workflow
│   │   ├── usage-reports.md      # OpenCode/Hermes report modes
│   │   └── pipeline.md           # 4-stage pipeline details
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

## Pipeline

4-stage pipeline: Ingest → Fill → Log → Lint.

```
1. INGEST → 2. FILL → 3. LOG → 4. LINT
(script)    (LLM)    (LLM)   (script)
```

See [Pipeline details](docs/workflows/pipeline.md) for stage-by-stage actions and lint check categories.

## Important Rules

- Never modify files in `data/raw/`. They are immutable after creation. Use `kb-lint-wiki --check-immutability` to enforce: git-status must not show modifications, `captured_at` must be ≤ file mtime (60s tolerance), and required raw frontmatter fields (`source_url`, `type`, `captured_at`, `contributor`) are always validated.
- `data/wiki/` pages must always list their `sources:` in frontmatter.
- Keep `data/log.md` updated on every operation.
- Lint must pass (0 errors) before committing wiki changes.
- Handoff documents are stored in `data/handoffs/` and tracked via git.
- Use uv for package management

## Privacy

`data/` is a local-only nested git repository. It is never pushed to remote.

- Outer `.gitignore` excludes `data/`
- `data/.git` is independent from outer repo
- All raw sources and wiki pages stay local
- Handoff documents (which may contain sensitive decisions) stay local

Never commit `data/` contents to the outer repository.

## Skills

- `knowledgebase-initialize` — initialize `data/`, verify tooling, and propose cron jobs for approval.

## Documentation

- [Documentation Index](docs/README.md) — read order and document map
- [Architecture](docs/architecture.md) — repository layout and memory layers
- [Pipeline](docs/workflows/pipeline.md) — 4-stage pipeline (Ingest → Fill → Log → Lint), commands, lint categories
- [Cron Jobs](docs/workflows/cron-jobs.md) — scheduling, locking, wrappers, failure policy
- [Usage Reports](docs/workflows/usage-reports.md) — OpenCode, Hermes, combined report modes
- [Periodic Memory Workflow](docs/workflows/periodic-memory-workflow.md) — daily, weekly, monthly memory workflow for cron agents
- [Frontmatter Conventions](docs/reference/frontmatter.md) — Raw, Wiki, Handoff frontmatter schemas
- [Wiki Categories](docs/reference/wiki-categories.md) — 7 categories, naming, wikilinks, tags
- [Handoff System](docs/workflows/handoff-system.md) — Roles, status, promotion, frontmatter
- [Commands](docs/reference/commands.md) — kb-mcp, kb-lint-wiki, kb-lint-handoff

## Reference

- Handoff system spec: external local reference, not required for normal operation.
- Migration plan: `.sisyphus/plans/memory-workflow-migration-v0.md` if present.
