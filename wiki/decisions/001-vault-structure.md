---
type: decision
created: "2026-04-15"
updated: "2026-04-15"
sources: []
graph_nodes: []
tags: [decision]
---

# 001 - 3-Layer LLM Wiki Architecture

## Context

Personal knowledge base that compounds over time. Sources include GitHub repos
(CLAUDE.md, issues, PRs), Desktop Chatbot conversations, calendar, web clippings.
Needs to be queryable by LLM agents via MCP (Phase 2).

## Decision

Adopt 3-layer architecture:
- **raw/** - Immutable source documents with YAML frontmatter for provenance
- **wiki/** - LLM-generated curated pages (entities, concepts, summaries, decisions, Q&A)
- **graphify-out/** - Knowledge graph build artifacts, kept separate from wiki/

Key separations:
- `graphify-out/wiki/` (auto-generated, overwritten) vs `wiki/` (curated, stable)
- Raw sources organized by type, not by date
- Wiki pages organized by function, not by source

## Consequences

- All raw files must have standardized frontmatter (graphify propagates it to graph nodes)
- Wiki pages are regenerable from graph.json — they are derived, not primary
- graphify-out/ should be .gitignored (build artifact)
- MCP server (Phase 2) serves graph.json + LLM layer for intelligent queries
