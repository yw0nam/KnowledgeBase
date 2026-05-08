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
├── CLAUDE.md                     Full schema + pipeline definition
├── README.md                     This file
└── .gitignore                    Excludes data/

data/                             Nested git repo (local-only)
├── raw/
│   ├── github/                   CLAUDE.md, Issues, PRs
│   ├── conversations/            Desktop Chatbot history
│   ├── calendar/                 Calendar events
│   ├── web/                      Web clippings
│   ├── manual/                   Hand-dropped files
│   └── handoffs/                 Handoff documents
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

### 1. Ingest

Collect raw sources into `data/raw/`.

```bash
./scripts/ingest-github.sh owner/repo    # GitHub CLAUDE.md + Issues + PRs
# or drop files into data/raw/manual/
```

### 2. Fill

LLM reads raw files and writes wiki pages to `data/wiki/`.

### 3. Log

Append operation record to `data/log.md`.

### 4. Lint

Validate wiki pages and handoff documents.

```bash
kb-lint-wiki                      # errors only = fail
kb-lint-wiki --strict             # warnings also = fail
kb-lint-handoff                   # validate handoffs
```

## Conventions

### Frontmatter — Raw files

```yaml
---
source_url: "https://..."
type: github_issue | claude_md | conversation | calendar_event | web_article | manual
captured_at: "2026-04-15T09:00:00Z"
author: "who wrote it"
contributor: "contributor name"
tags: []
---
```

### Frontmatter — Wiki pages

Always block style for lists. Never quote scalars except dates.

```yaml
---
type: entity | concept | decision | question | improvement | checklist | summary
created: "2026-04-15"
updated: "2026-04-15"
sources:
  - raw/github/issues/repo_42.md
aliases: []
tags: []
---
```

### Naming

- Raw: `{repo}_{number}.md`, `chat_{timestamp}.md`, `event_{date}_{slug}.md`
- Wiki entities: `{subject}/{YYYY-MM}/PascalCase.md`
- Wiki concepts: `Snake_Case.md` (flat)
- Summaries: ISO (`2026-W16.md`, `2026-04.md`)

### Wikilinks

- `[[FileName]]` or `[[FileName|Display Text]]`. Never `.md` extension.
- Only link to pages that exist. No page → plain text.

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
| `data/raw/handoffs/` | Handoff documents |

## More

See `CLAUDE.md` for full schema, frontmatter conventions, handoff system details, and reference links.
