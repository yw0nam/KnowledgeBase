# Commands

Updated: 2026-05-18

## 1. Synopsis

- **Purpose**: KnowledgeBase CLI commands for validating wiki/handoff content and generating reports.
- **I/O**: Shell command → lint report (exit 0 = pass, non-zero = fail).

## 2. Core Logic

### kb-lint-wiki

Validate wiki pages.

```bash
kb-lint-wiki                      # errors only
kb-lint-wiki --strict             # errors + warnings (auto-enables --check-immutability)
kb-lint-wiki --check-immutability # enforce raw file immutability
```

### kb-lint-handoff

Validate handoff documents.

```bash
kb-lint-handoff
```

### kb-wiki-index

Regenerate `data/wiki/INDEX.md`, the auto-built table of contents grouping all
wiki pages by category. Idempotent — running on an unchanged wiki rewrites
nothing. `kb-lint-wiki` will ERROR if INDEX.md is stale.

```bash
kb-wiki-index
```

## 3. Usage

Run the typical workflow in order:

```bash
# Step 1: Ingest sources
./scripts/ingest-github.sh owner/repo

# Step 2: Write wiki pages (LLM step, no command)

# Step 3a: Refresh global TOC (after any wiki page change)
kb-wiki-index

# Step 3b: Validate wiki
kb-lint-wiki

# Step 4: Validate handoffs
kb-lint-handoff

# Step 5: Commit when both lints exit 0
cd data
git add raw/ wiki/ log.md
git commit -m "ingest: [source] description"
```

For cron-based daily, weekly, and monthly memory workflows, read
`docs/workflows/periodic-memory-workflow.md` before running the pipeline.

---

## Appendix

### A. Troubleshooting

**kb-lint-wiki errors on dead wikilink**
Fix the link or use plain text instead of a wikilink.

**kb-lint-wiki --check-immutability fails**
A raw file was modified. Revert the raw file to its original state.

**kb-lint-handoff fails on missing frontmatter field**
Add the missing field to the handoff document frontmatter.

### B. PatchNote

- 2026-05-18: Added kb-wiki-index — generates `data/wiki/INDEX.md`. Enforced by `kb-lint-wiki`.
- 2026-05-18: Removed kb-mcp (MCP server retired in favor of direct CLI usage by Claude Code agents).
- 2026-05-18: Added pointer to periodic memory workflow for cron agents.
- 2026-05-08: Initial split from CLAUDE.md and restructured to follow docs/CLAUDE.md Standard Document Structure.
