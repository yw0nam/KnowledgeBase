# KnowledgeBase

Personal LLM Wiki built on Obsidian + Graphify. A 3-layer knowledge system that compounds over time.

## Quick Start

### 1. Ingest Data

Add sources to `raw/` using the ingest scripts:

```bash
# GitHub: CLAUDE.md + Issues + PRs
./scripts/ingest-github.sh owner/repo [owner/repo2 ...]

# Example:
./scripts/ingest-github.sh yw0nam/DesktopMatePlus
```

Or use graphify CLI directly:
```bash
/graphify add https://url.com --author "Name"
```

### 2. Build Knowledge Graph

```bash
/graphify raw/ --update --wiki --obsidian --obsidian-dir .
```

This generates:
- `graphify-out/graph.json` — the knowledge graph
- `graphify-out/graph.html` — interactive visualization
- `graphify-out/wiki/` — auto-generated community pages
- `GRAPH_REPORT.md` — analysis and suggestions

### 3. Generate Curated Wiki

```bash
/graphify-wiki-gen
```

Or manually:
```bash
python3 scripts/generate-wiki.py
```

This creates:
- `wiki/entities/` — one page per god node (most connected)
- `wiki/concepts/` — one page per community cluster
- `wiki/index.md` — master index

### 4. Open in Obsidian

Open this directory in Obsidian. Browse:
- Graph view → see all connections
- `wiki/index.md` → enter via curated index
- `wiki/entities/` — projects, tools, people
- `wiki/concepts/` — abstract ideas and clusters

## Architecture

### 3 Layers

```
raw/              ← Immutable sources (frontmatter metadata)
  ├── github/
  ├── conversations/
  ├── calendar/
  ├── web/
  └── manual/

wiki/             ← LLM-generated (curated)
  ├── entities/
  ├── concepts/
  ├── summaries/
  ├── decisions/
  └── questions/

graphify-out/     ← Build artifacts (ephemeral)
  ├── graph.json
  ├── graph.html
  └── wiki/        (auto-generated, overwritten on rebuild)
```

### Key Principles

- **raw/** is immutable. Files added once, never modified.
- **wiki/** is regenerable from graph.json. Always current.
- **graphify-out/** is build output. Add to `.gitignore`.
- Every raw file has YAML frontmatter with provenance (source_url, author, captured_at).
- Every wiki page cites its sources in frontmatter.
- Use `[[wikilinks]]` throughout. Graph lives in connections.

## Operations

| Task | Command | Output |
|------|---------|--------|
| Ingest GitHub | `./scripts/ingest-github.sh owner/repo` | Files in `raw/github/` |
| Add web source | `/graphify add <url>` | File in `raw/web/`, git diff |
| Build graph | `/graphify raw/` | `graphify-out/graph.json` + HTML |
| Incremental build | `/graphify raw/ --update` | Delta changes only (fast) |
| Generate wiki | `/graphify-wiki-gen` | Entity + concept pages |
| Query graph | `/graphify query "question"` | Terminal output + suggestion to save |
| Find path | `/graphify path "A" "B"` | Shortest path visualization |
| Explain node | `/graphify explain "concept"` | Plain-language summary |

## Workflow

### Daily: Ingest + Build

```bash
# 1. Add new sources
./scripts/ingest-github.sh owner/repo
/graphify add https://article.com

# 2. Rebuild graph (incremental)
/graphify raw/ --update --wiki

# 3. Update wiki
/graphify-wiki-gen

# 4. Commit
git add raw/ wiki/ log.md
git commit -m "ingest: [type] Added content"
```

### Weekly: Curate + Summarize

```bash
# 1. Open graph.html in browser, explore
# 2. Read suggested questions from GRAPH_REPORT.md
# 3. Run interesting queries:
/graphify query "What connects Community 0 to Community 1?"
# 4. Save results to wiki/questions/
# 5. Create summary pages: wiki/summaries/weekly/2026-W15.md
```

### Monthly: Lint + Refactor

```bash
# Check health
scripts/lint.sh
# Look for:
# - Broken wikilinks
# - Orphan pages (no incoming links)
# - Missing frontmatter
# - Stale claims (contradicted by newer sources)
```

## Conventions

### Frontmatter - Raw Files

```yaml
---
source_url: "https://..."
type: "github_issue" | "claude_md" | "conversation" | "calendar_event" | "web_article" | "manual"
captured_at: "2026-04-15T09:00:00Z"
author: "who wrote it"
contributor: "nam-young-woo"
tags: []
---
```

### Frontmatter - Wiki Pages

```yaml
---
type: "entity" | "concept" | "summary" | "decision" | "question"
created: "2026-04-15"
updated: "2026-04-15"
sources: ["raw/github/issues/repo_42.md"]
graph_nodes: ["node_id_1"]
aliases: []
tags: []
---
```

### Naming

- Raw files: `{repo}_{issue_number}.md`, `chat_{timestamp}.md`, `event_{date}_{slug}.md`
- Wiki entities: `PascalCase.md` (e.g., `DesktopMatePlus.md`)
- Wiki concepts: `Snake_Case.md` (e.g., `Knowledge_Graph.md`)
- Summaries: ISO dates (e.g., `2026-W15.md`, `2026-04.md`)

## Phase 2: MCP Server

An MCP server wrapping graphify + LLM (Claude Code or OpenCode) will expose:
- `query_graph(question)` — graphify query + LLM search → answer with sources
- `ingest_url(url, author?)` — add URL + rebuild graph
- Future: vector search, batch queries, multi-hop reasoning

Coming soon.

## Files Overview

- `CLAUDE.md` — Schema definition (read this first)
- `log.md` — Append-only operation record
- `wiki/index.md` — Entry point for navigation
- `raw/` — Source documents (organized by type)
- `wiki/` — Curated pages (organized by function)
- `graphify-out/` — Build artifacts
- `scripts/` — Automation
- `templates/` — Frontmatter templates

## Troubleshooting

**Q: graph.json is stale**  
A: Run `/graphify raw/ --update --wiki` to rebuild incrementally.

**Q: Wiki pages have broken links**  
A: Run `scripts/lint.sh` to find orphans. Update frontmatter `sources:` if pages were moved.

**Q: Graph is too large to visualize**  
A: Graphify skips HTML for graphs > 5000 nodes. Use `--cluster-only` to re-cluster without re-extracting. Or use this Obsidian vault view instead.

**Q: raw/ and wiki/ have similar pages**  
A: This is normal. raw/ has immutable sources. wiki/ has curated, regenerable pages. They serve different purposes.

## See Also

- `CLAUDE.md` — Full schema and conventions
- `log.md` — Chronological operation history
- `graphify-out/GRAPH_REPORT.md` — Latest graph analysis
