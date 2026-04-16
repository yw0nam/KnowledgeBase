# KnowledgeBase

Personal LLM Wiki. Raw sources go in, LLM writes wiki pages, lint keeps them honest.

## Architecture

두 개의 git repo로 분리.

```
KnowledgeBase/          ← root git (scripts, config — 공개 가능)
├── scripts/
│   ├── ingest-github.sh
│   └── lint-wiki.py
├── CLAUDE.md
├── README.md
└── data/               ← 별도 git (content — 로컬 전용)
    ├── raw/
    │   ├── github/         CLAUDE.md, Issues, PRs
    │   ├── conversations/  Desktop Chatbot history
    │   ├── calendar/       Calendar events
    │   ├── web/            Web clippings
    │   └── manual/         Anything dropped by hand
    ├── wiki/
    │   ├── entities/       Named objects (projects, tools, people)
    │   ├── concepts/       Abstract ideas (patterns, protocols)
    │   ├── summaries/      Time/project rollups
    │   ├── decisions/      Architecture Decision Records
    │   └── questions/      Saved Q&A
    └── log.md
```

## Pipeline

```
1.INGEST → 2.FILL → 3.LINT → 4.LOG
(script)    (LLM)  (script)  (LLM)
```

### 1. Ingest

```bash
./scripts/ingest-github.sh owner/repo    # GitHub CLAUDE.md + Issues + PRs
# or drop files into data/raw/manual/
```

### 2. Fill

`git -C data/ status`로 새 raw 파일 파악 후 Claude가 직접 wiki 페이지 작성.

### 3. Lint

```bash
uv run python3 scripts/lint-wiki.py               # errors = fail
uv run python3 scripts/lint-wiki.py --strict      # warnings = fail too
```

### 4. Log + Commit

```bash
# LLM appends to data/log.md after lint passes
cd data && git add raw/ wiki/ log.md
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
- Wiki entities: `{project}/{YYYY-MM}/PascalCase.md`
- Wiki concepts: `Snake_Case.md` (flat)
- Summaries: ISO (`2026-W16.md`, `2026-04.md`)

### Wikilinks

- `[[FileName]]` or `[[FileName|Display Text]]`. Never `.md` extension.
- Only link to pages that exist. No page → plain text.

## Files

| File | Role |
|---|---|
| `CLAUDE.md` | Schema + pipeline definition |
| `data/log.md` | Append-only operation record |
| `data/wiki/index.md` | Entry point |
| `scripts/ingest-github.sh` | Step 1: GitHub data collection |
| `scripts/lint-wiki.py` | Step 3: validation |
