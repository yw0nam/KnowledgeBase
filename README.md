# KnowledgeBase

Personal LLM Wiki. Raw sources go in, LLM writes wiki pages, lint keeps them honest.

## Architecture

```
KnowledgeBase/
├── scripts/
│   ├── ingest-github.sh
│   └── lint-wiki.py
├── src/kb_mcp/          MCP server + CLI tools
├── raw/
│   ├── github/          CLAUDE.md, Issues, PRs
│   ├── conversations/   Desktop Chatbot history
│   ├── calendar/        Calendar events
│   ├── web/             Web clippings
│   └── manual/          Anything dropped by hand
├── wiki/
│   ├── entities/        Named objects ({subject}/{YYYY-MM}/)
│   ├── concepts/        Abstract ideas (patterns, protocols)
│   ├── summaries/       Time/subject rollups
│   ├── decisions/       Architecture Decision Records
│   └── questions/       Saved Q&A
├── graphify-out/        Build artifacts (gitignored)
│   └── graph.json       Knowledge graph
├── log.md
├── CLAUDE.md
└── README.md
```

## Pipeline

```
1.INGEST → 2.GRAPH → 3.FILL → 4.LINT → 5.LOG
(script)  (graphify)  (LLM)  (script)  (LLM)
```

### 1. Ingest

```bash
./scripts/ingest-github.sh owner/repo    # GitHub CLAUDE.md + Issues + PRs
# or drop files into raw/manual/
```

### 2. Graph

```
/graphify raw/ --update --no-viz
```

`--update`: only re-extract new files (uses cache). `--no-viz`: skip HTML.
Result: `graphify-out/graph.json`

### 3. Fill

Use `uv run python -m kb_mcp.cli.diff_raw` to find unprocessed raw files → read `graphify-out/graph.json` → LLM writes wiki pages.

### 4. Lint

```bash
uv run python3 scripts/lint-wiki.py               # errors = fail
uv run python3 scripts/lint-wiki.py --strict      # warnings = fail too
```

### 5. Log + Commit

```bash
# LLM appends to log.md after lint passes
git add raw/ wiki/ log.md
git commit -m "ingest: [source] description"
```

## Conventions

### Frontmatter — Raw files

```yaml
---
source_url: "https://..."
type: github_issue | claude_md | conversation | calendar_event | web_article | manual
captured_at: "2026-04-15T09:00:00Z"
author: "who wrote it"
contributor: "nam-young-woo"
tags: []
---
```

### Frontmatter — Wiki pages

Always block style for lists. Never quote scalars except dates.

```yaml
---
type: entity
created: "2026-04-15"
updated: "2026-04-15"
sources:
  - raw/github/issues/repo_42.md
aliases: []
tags: [architecture, entity, project]
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

## Files

| File | Role |
|---|---|
| `CLAUDE.md` | Schema + pipeline definition |
| `log.md` | Append-only operation record |
| `graphify-out/graph.json` | Knowledge graph (build artifact) |
| `scripts/ingest-github.sh` | Step 1: GitHub data collection |
| `scripts/lint-wiki.py` | Step 4: validation |
