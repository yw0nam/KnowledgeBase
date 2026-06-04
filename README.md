# KnowledgeBase

Personal LLM wiki. Raw sources go in, LLM writes wiki pages, lint keeps them honest.

## Architecture

KnowledgeBase separates code from data:

- **Outer repo** (`KnowledgeBase/`) — Code, lint tools, templates, documentation. Public-safe.
- **Generated data export** (`data/`) — Raw sources, wiki pages, handoff documents. DB-canonical; `data/db/state.db` is the source of truth.

```
KnowledgeBase/
├── src/kb/                   CLI tools (lint, daily reports)
├── scripts/
│   └── ingest-github.sh          GitHub source collection
├── .claude/skills/               Runtime workflow contracts + bundled templates
│   ├── wiki-authoring/             Wiki page templates and authoring rules
│   ├── wiki-approval/              review_status lifecycle workflow
│   ├── knowledgebase-initialize/   Setup workflow
│   └── usage-report-setup/         Usage report mode workflow
├── docs/raw/                Raw source frontmatter templates
├── CLAUDE.md                     LLM entry point and project skill map
├── README.md                     This file
└── .gitignore                    Excludes data/

data/                             Generated data export (DB-canonical; see docs/db-canonical.md)
├── db/
│   └── state.db                  Canonical SQLite database (Source of Truth)
├── raw/
│   ├── github/                   CLAUDE.md, Issues, PRs
│   ├── conversations/            Desktop Chatbot history
│   ├── calendar/                 Calendar events
│   ├── web/                      Web clippings
│   └── manual/                   Hand-dropped files
├── handoffs/                     Handoff documents
├── wiki/
│   ├── entities/                 Named objects ({subject}/{YYYY-MM}/)
│   ├── concepts/                 Abstract ideas (flat)
│   ├── decisions/                Architecture Decision Records
│   ├── questions/                Saved Q&A
│   ├── improvements/             Open-ended improvements
│   ├── checklists/               Operational checklists
│   └── summaries/                Time/subject rollups
├── rejected/                     Rejected wiki pages (created by DB API)
└── log.md                        Operation record
```

## Workflows

Project workflows live in `.claude/skills/`. Use `wiki-authoring` for source-backed wiki edits, `wiki-approval` for review lifecycle work, `memory-report` for daily/weekly/monthly synthesis, and `handoff-document` for handoffs.

## Privacy

`data/` is private and must never be pushed to the outer repository or a public remote.
`data/db/state.db` is the canonical store — see `docs/db-canonical.md` for the architecture.

- Outer `.gitignore` excludes `data/`
- All raw sources and wiki pages stay private
- Handoff documents (sensitive decisions) stay private

## Quick Start

### Install

```bash
uv sync
```

### Ingest sources

```bash
./scripts/ingest-github.sh owner/repo
```

### Write wiki

Use `.claude/skills/wiki-authoring/SKILL.md`; read `data/raw/` and write source-backed pages to `data/wiki/`.

### Validate

```bash
kb-lint
```

### Commit

Writes go through the DB API — Markdown files under `data/` are generated exports.
Changes to the outer repo (code, docs, skills) are committed as usual.

## Files

| File | Role |
|---|---|
| `CLAUDE.md` | LLM entry point and project skill map |
| `scripts/ingest-github.sh` | GitHub source collection |
| `src/kb/cli/lint.py` | Wiki + handoff validation |
| `src/kb/cli/db_ttl_sweep.py` | Auto-reject stale unprocessed pages |
| `src/kb/web/` | DB-canonical API server (`kb-web`) |
| `data/log.md` | Operation record |
| `data/raw/` | Immutable sources |
| `data/wiki/` | LLM-generated pages |
| `data/handoffs/` | Handoff documents |

## Documentation

- [Documentation Index](docs/README.md) — Skill routing and design document map
- [Architecture](docs/architecture.md) — Repository layout and memory layers
- [Frontmatter](docs/reference/frontmatter.md) — Human schema reference; runtime rules live in skills
- [Wiki Categories](docs/reference/wiki-categories.md) — Human category reference; runtime uses `wiki-authoring`
- [Commands](docs/reference/commands.md) — Full CLI command reference

See [CLAUDE.md](CLAUDE.md) for the LLM entry point.
