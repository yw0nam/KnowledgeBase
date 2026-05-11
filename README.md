# KnowledgeBase

Personal LLM wiki. Raw sources go in, LLM writes wiki pages, lint keeps them honest.

## Architecture

KnowledgeBase separates code from data:

- **Outer repo** (`KnowledgeBase/`) — Code, lint tools, templates, documentation. Public-safe.
- **Nested repo** (`data/`) — Raw sources, wiki pages, handoff documents. Local-only, never pushed.

```
KnowledgeBase/
├── src/kb_mcp/                   MCP server + CLI tools
├── scripts/
│   └── ingest-github.sh          GitHub source collection
├── templates/                    Frontmatter + handoff templates
│   ├── wiki/                       Wiki page templates (entity, concept, decision, …)
│   │   └── summaries/              Summary subtypes (daily, weekly, …)
│   ├── handoff/                    Handoff templates (task, final, readme)
│   └── raw/                        Raw source frontmatter
├── CLAUDE.md                     Full schema + pipeline definition
├── README.md                     This file
└── .gitignore                    Excludes data/

data/                             Nested git repo (local-only)
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
└── log.md                        Operation record
```

## Pipeline

4-stage pipeline:

```
1. INGEST → 2. FILL → 3. LOG → 4. LINT
(script)    (LLM)    (LLM)   (script)
```

See [docs/pipeline.md](docs/pipeline.md) for stage-by-stage details, bash commands, and lint check categories.

## Privacy

`data/` is local-only. Never pushed to remote.

- Outer `.gitignore` excludes `data/`
- All raw sources and wiki pages stay local
- Handoff documents (sensitive decisions) stay local

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

Read `data/raw/` and write pages to `data/wiki/`.

### Validate

```bash
kb-lint-wiki
kb-lint-handoff
```

### Commit

```bash
cd data
git add raw/ wiki/ log.md
git commit -m "ingest: [source] description"
```

## Files

| File | Role |
|---|---|
| `CLAUDE.md` | Full schema + pipeline definition |
| `scripts/ingest-github.sh` | GitHub source collection |
| `src/kb_mcp/cli/lint_wiki.py` | Wiki validation |
| `src/kb_mcp/cli/lint_handoff.py` | Handoff validation |
| `data/log.md` | Operation record |
| `data/raw/` | Immutable sources |
| `data/wiki/` | LLM-generated pages |
| `data/handoffs/` | Handoff documents |

## Documentation

- [Pipeline details](docs/pipeline.md) — Full pipeline stages and lint check categories
- [Frontmatter](docs/frontmatter.md) — Raw, Wiki, and Handoff frontmatter schemas
- [Wiki Categories](docs/wiki-categories.md) — 7 categories, naming, wikilinks, tags
- [Handoff System](docs/handoff-system.md) — Roles, status, promotion
- [Commands](docs/commands.md) — Full CLI command reference

See [CLAUDE.md](CLAUDE.md) for the LLM entry point.
