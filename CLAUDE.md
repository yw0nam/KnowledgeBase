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
├── scripts/
│   └── ingest-github.sh          # GitHub source collection
├── templates/                    # Frontmatter + handoff templates
├── pyproject.toml
├── CLAUDE.md                     # This file
├── README.md
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
│   ├── manual/                   # Hand-dropped files
│   └── handoffs/                 # Handoff documents (task-based)
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

4-stage pipeline. No graph stage.

```
1. INGEST → 2. FILL → 3. LOG → 4. LINT
(script)    (LLM)    (LLM)   (script)
```

### 1. Ingest — Data collection

Collect raw sources into `data/raw/`.

```bash
# GitHub sources (CLAUDE.md, Issues, PRs)
./scripts/ingest-github.sh owner/repo

# Or drop files manually into data/raw/manual/
```

Result: markdown files with frontmatter in `data/raw/{type}/`.

### 2. Fill — LLM writes wiki

Read raw files and create or update wiki pages in `data/wiki/`.

- Identify unprocessed raw files
- Read each raw file
- Create or update the relevant wiki page
- Ensure `sources:` in frontmatter references actual raw file paths
- Only use wikilinks to pages that exist

### 3. Log — Record operations

Append to `data/log.md` after wiki changes. Include:
- What was ingested
- Which wiki pages were created/updated
- Any decisions or issues encountered

### 4. Lint — Validation

```bash
# Lint wiki pages
kb-lint-wiki                      # errors only = fail
kb-lint-wiki --strict             # warnings also = fail

# Lint handoff documents
kb-lint-handoff
```

Checks (ERROR = cannot commit):
- Dead wikilinks, `.md` in target, LaTeX/HTML, frontmatter format, stale sources, missing frontmatter

Checks (WARN = informational):
- Self-links, unfilled placeholders, orphan pages, empty sections

## Frontmatter Conventions

### Raw files

```yaml
---
source_url: "https://..."
type: github_issue | claude_md | conversation | calendar_event | web_article | manual
captured_at: "2026-04-15T09:00:00Z"
author: "who wrote it"
contributor: "who added it"
tags: []
---
```

### Wiki pages

Always use YAML block style for lists. Never quote scalar values except dates.

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

Note: `sources:` paths are relative to `data/` (the parent of `data/wiki/`). Use `raw/...`, not `data/raw/...`.

### Handoff documents

```yaml
---
handoff_id: <task-slug>:<subject>:<role>:01
task_slug: <task-slug>
subject: <subject-or-null>
role: main_gateway | research | structuring | execution | verification
handoff_seq: 1
status: draft | ready | consumed | superseded
security:
  contains_secrets: false
  redaction_status: unchecked
promotion: null | skill_candidate | memory | wiki_entity | wiki_concept
---
```

## Wiki Categories

### Entities
Named objects grouped by subject and month. Path: `entities/{subject}/{YYYY-MM}/PascalCase.md`.

### Concepts
Abstract ideas, patterns, protocols. Flat directory. Path: `concepts/Snake_Case.md`.

### Decisions
Architecture Decision Records. Closed/finalized. Path: `decisions/ADR_{number}.md`.

### Questions
Saved Q&A. Path: `questions/{YYYY-MM}/Question_Title.md`.

### Improvements
Open-ended improvement ideas. Status: draft, in_progress, proposed, deferred. Path: `improvements/{YYYY-MM}/Improvement_Title.md`.

### Checklists
Operational checklists. Path: `checklists/Checklist_Name.md`.

### Summaries
Time/subject rollups. Path: `summaries/{daily|weekly|monthly|migration}/{YYYY-MM-DD|YYYY-Www|YYYY-MM}.md`.

## Handoff System v0

Handoff documents track work delegation and decision-making. See `/home/spow12/hermes_optimize/handoff.md` for full spec.

### Roles

- **main_gateway** — User request interpretation, delegation decision, final response
- **research** — Source survey, evidence gathering, conflicting claims
- **structuring** — Schema design, content merging, editorial decisions
- **execution** — Implementation, file changes, test results
- **verification** — Criteria definition, findings, pass/fail decision

### Status

- **draft** — In progress
- **ready** — Ready for next agent
- **consumed** — Received and acted upon
- **superseded** — Replaced by newer handoff

### Promotion

Candidates for escalation:
- `skill_candidate` — Reusable workflow for future automation
- `memory` — Important decision or pattern to preserve
- `wiki_entity` — Becomes a wiki page
- `wiki_concept` — Becomes a concept page

## Naming Conventions

### Raw files
- GitHub: `{repo}_{issue_number}.md`
- Conversations: `chat_{ISO_timestamp}.md`
- Calendar: `event_{date}_{slug}.md`
- Handoffs: `{subject}_{role}_handoff_{seq}.md` or `{role}_handoff_{seq}.md`

### Wiki entities
`{subject}/{YYYY-MM}/PascalCase.md` (e.g., `DesktopMatePlus/2026-04/PR36_HumanInTheLoopApprovalGate.md`)

### Wiki concepts
`Snake_Case.md` (flat, e.g., `Agent_Middleware_Implementation_Stack.md`)

### Wiki summaries
ISO date/week (e.g., `2026-W16.md`, `2026-04.md`)

## Wikilinks (Obsidian)

- Use `[[FileName]]` or `[[FileName|Display Text]]`. Never include `.md` extension.
- Only link to pages that exist. If a concept has no wiki page, use plain text.
- Raw sources are cited in frontmatter `sources:` array, never as inline links.

## Tags

Flat namespace. Common: project, tool, pattern, decision, person, event, migration.

## Important Rules

- Never modify files in `data/raw/`. They are immutable after creation.
- `data/wiki/` pages must always list their `sources:` in frontmatter.
- Keep `data/log.md` updated on every operation.
- Lint must pass (0 errors) before committing wiki changes.
- Handoff documents are stored in `data/raw/handoffs/` and tracked via git.

## Commands

### kb-mcp
MCP server. Exposes tools for ingest and other operations.

```bash
kb-mcp
```

### kb-lint-wiki
Validate wiki pages.

```bash
kb-lint-wiki                      # errors only
kb-lint-wiki --strict             # errors + warnings
```

### kb-lint-handoff
Validate handoff documents.

```bash
kb-lint-handoff
```

## Privacy

`data/` is a local-only nested git repository. It is never pushed to remote.

- Outer `.gitignore` excludes `data/`
- `data/.git` is independent from outer repo
- All raw sources and wiki pages stay local
- Handoff documents (which may contain sensitive decisions) stay local

Never commit `data/` contents to the outer repository.

## Skills

Currently NONE. All previous automation skills were removed during migration to memory-workflow v0. New skills will be authored after 2-3 operating cycles complete.

## Reference

- Handoff system spec: `/home/spow12/hermes_optimize/handoff.md`
- Migration plan: `/home/spow12/codes/KnowledgeBase/.sisyphus/plans/memory-workflow-migration-v0.md`
