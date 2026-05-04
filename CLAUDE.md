# KnowledgeBase

Personal LLM Wiki. Raw sources go in, LLM writes wiki pages, lint keeps them honest.

## Structure

Everything lives in one flat repository at the project root.

- `raw/` - Immutable sources. Never modify after creation. Subdirs by type:
  - `github/claude-md/` - CLAUDE.md files from repos (`{owner}_{repo}_CLAUDE.md`)
  - `github/issues/` - Issues + PRs (`{repo}_{number}.md`)
  - `conversations/` - Desktop Chatbot history (`{YYYY-MM}/chat_{timestamp}.md`)
  - `calendar/` - Calendar events (`{YYYY-MM}/event_{date}_{slug}.md`)
  - `web/` - Web clippings (Obsidian Web Clipper output)
  - `manual/` - Anything dropped by hand
- `wiki/` - LLM-generated pages. Subdirs:
  - `entities/{subject}/{YYYY-MM}/` - subject entities grouped by month
  - `entities/{subject}/_index.md` - Subject hub page
  - `concepts/` - Abstract ideas, cross-cutting (flat, no subdirs)
  - `summaries/` - Time/subject rollups (weekly/, monthly/, subjects/)
  - `decisions/` - Architecture Decision Records
  - `questions/` - Saved Q&A
- `graphify-out/` - Build artifacts (gitignored). `graph.json` is the knowledge graph.
- `log.md` - Append-only chronological record of operations.

## Conventions

### Frontmatter - Raw files

```yaml
---
source_url: "https://..."
type: "github_issue" | "claude_md" | "conversation" | "calendar_event" | "web_article" | "manual"
captured_at: "2026-04-15T09:00:00Z"
author: "who wrote it"
contributor: "who added it"
tags: []
---
```

### Frontmatter - Wiki pages

Always use YAML block style for lists. Never quote scalar values except dates.

```yaml
---
type: entity
created: "2026-04-15"
updated: "2026-04-15"
sources:
  - raw/github/issues/repo_42.md
aliases: []
tags: []
---
```

### Naming

- Raw: `{repo}_{issue_number}.md`, `chat_{ISO_timestamp}.md`, `event_{date}_{slug}.md`
- Wiki entities: `{subject}/{YYYY-MM}/PascalCase.md` (e.g. `DesktopMatePlus/2026-04/PR36_HumanInTheLoopApprovalGate.md`)
- Wiki subject hub: `{subject}/_index.md` (lists all pages by month)
- Wiki concepts: Snake_Case, flat (`Agent_Middleware_Implementation_Stack.md`)
- Wiki summaries: ISO date/week (`2026-W16.md`, `2026-04.md`)

### Wikilinks (Obsidian)

- Use `[[FileName]]` or `[[FileName|Display Text]]`. Never include `.md` extension.
- Only link to pages that exist. If a concept has no wiki page, use plain text.
- Raw sources are cited in frontmatter `sources:` array, never as inline links.

### Tags

Flat namespace. Common: project, tool, pattern, decision, person, event.

## Pipeline

5-stage pipeline.

```
1.INGEST → 2.GRAPH → 3.FILL → 4.LINT → 5.LOG
(script)   (graphify)  (LLM)  (script)  (LLM)
```

### 1. Ingest — Data collection

```bash
./scripts/ingest-github.sh owner/repo    # GitHub CLAUDE.md + Issues + PRs
# or drop files into raw/manual/
```

Result: markdown files with frontmatter in `raw/{type}/`.

### 2. Graph — Knowledge graph build

```
/graphify raw/ --update --no-viz
```

Result: `graphify-out/graph.json` (nodes, edges, communities).
`--update`: only re-extract newly added files (uses cache).
`--no-viz`: skip HTML generation.

### 3. Fill — LLM writes wiki

Use `uv run python -m kb_mcp.cli.diff_raw` to identify raw files needing processing, then:

- Read `graphify-out/graph.json` to understand relationships
- Read each raw file and create or update the relevant wiki page
- `sources:` in frontmatter must reference actual raw file paths
- Only use wikilinks to pages that exist

### 4. Lint — Validation

```bash
uv run python3 scripts/lint-wiki.py               # errors only = fail
uv run python3 scripts/lint-wiki.py --strict      # warnings also = fail
```

Checks (ERROR = cannot commit):

- Dead wikilinks, `.md` in target, LaTeX/HTML, frontmatter format,
  stale sources, missing frontmatter

Checks (WARN = informational):

- Self-links, unfilled placeholders, orphan pages, empty sections

### 5. Log — Record

LLM appends to `log.md`. Only after lint PASSED.

## Important rules

- Never modify files in `raw/`. They are immutable after creation.
- `wiki/` pages must always list their `sources:` in frontmatter.
- Keep `log.md` updated on every operation.
- Lint must pass (0 errors) before committing wiki changes.

## Scripts

| Script | Role | Stage |
|---|---|---|
| `scripts/ingest-github.sh` | GitHub source collection | 1. Ingest |
| `scripts/lint-wiki.py` | Validation | 4. Lint |

## Skills

- **graphify** — Knowledge graph build. Trigger: `/graphify raw/ --update --no-viz`. Used in stage 2.
- **kb_init** (`.claude/skills/kb_init/SKILL.md`) — Initial setup + full graph build + write all wiki pages. Trigger: `/kb_init`
- **kb_update** (`.claude/skills/kb_update/SKILL.md`) — Incremental graph update + write wiki for new files only. Trigger: `/kb_update`
- **kb_search** (`.claude/skills/kb_search/SKILL.md`) — Graph-based question answering. Trigger: `/kb_search <question>`

When the user types `/kb_init`, invoke the Skill tool with `skill: "kb_init"` before doing anything else.
When the user types `/kb_update`, invoke the Skill tool with `skill: "kb_update"` before doing anything else.
When the user types `/kb_search`, invoke the Skill tool with `skill: "kb_search"` before doing anything else.
