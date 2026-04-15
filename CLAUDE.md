# KnowledgeBase

Personal LLM Wiki. Three layers: raw (immutable sources), wiki (LLM-generated),
graphify-out (knowledge graph).

## Structure

- `raw/` - Immutable sources. Never modify after creation. Subdirs by type:
  - `github/claude-md/` - CLAUDE.md files from repos (`{owner}_{repo}_CLAUDE.md`)
  - `github/issues/` - Issues + PRs (`{repo}_{number}.md`)
  - `conversations/` - Desktop Chatbot history (`{YYYY-MM}/chat_{timestamp}.md`)
  - `calendar/` - Calendar events (`{YYYY-MM}/event_{date}_{slug}.md`)
  - `web/` - Web clippings (Obsidian Web Clipper output)
  - `manual/` - Anything dropped by hand
- `wiki/` - LLM-generated pages. Subdirs:
  - `entities/` - Named objects (projects, tools, people)
  - `concepts/` - Abstract ideas (patterns, protocols)
  - `summaries/` - Time/project rollups (weekly/, monthly/, projects/)
  - `decisions/` - Architecture Decision Records
  - `questions/` - Saved Q&A (feedback loop into graph)
- `graphify-out/` - Build artifacts. `graph.json` is the knowledge graph.
  `graphify-out/wiki/` is auto-generated community pages (overwritten on rebuild).
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

```yaml
---
type: "entity" | "concept" | "summary" | "decision" | "question"
created: "2026-04-15"
updated: "2026-04-15"
sources: ["raw/github/issues/repo_42.md"]
graph_nodes: ["node_id"]
aliases: []
tags: []
---
```

### Naming

- Raw: `{repo}_{issue_number}.md`, `chat_{ISO_timestamp}.md`, `event_{date}_{slug}.md`
- Wiki entities: PascalCase (`DesktopMatePlus.md`)
- Wiki concepts: Snake_Case (`Knowledge_Graph.md`)
- Wiki summaries: ISO date/week (`2026-W16.md`, `2026-04.md`)

### Cross-references

Use `[[wikilinks]]`. Link to wiki pages, not raw files.
Raw sources are cited in frontmatter `sources:` array.

### Tags

Flat namespace. Common: project, tool, pattern, decision, person, event.

## Operations

### Ingest

1. Add source to `raw/{type}/` with proper frontmatter
2. Run `/graphify raw/ --update --wiki --obsidian --obsidian-dir .`
3. Update `wiki/` pages as needed (entities, concepts, summaries)
4. Append entry to `log.md`

### Query

Phase 2: MCP server wrapping graphify + LLM (claude code or opencode).
For now: `/graphify query "question"`, `/graphify path "A" "B"`, `/graphify explain "X"`

### Lint

Check: broken wikilinks, missing frontmatter, orphan pages, stale summaries.

## Important rules

- Never modify files in `raw/`. They are immutable after creation.
- `graphify-out/` is ephemeral build output. Do not manually edit.
- `wiki/` pages must always list their `sources:` in frontmatter.
- Keep `wiki/index.md` updated on every ingest.
- Keep `log.md` updated on every operation.

## Skills

- **graphify** (`.claude/skills/graphify/SKILL.md`) - any input to knowledge graph.
  Trigger: `/graphify`
  When invoked, run the graphify skill to build knowledge graphs from raw sources.

- **graphify-wiki-gen** (`.claude/skills/graphify-wiki-gen/SKILL.md`) - generate curated wiki from graph.
  Trigger: `/graphify-wiki-gen`
  When invoked, run Python script to generate wiki/entities and wiki/concepts from graphify-out/graph.json.
