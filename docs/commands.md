# Commands

Updated: 2026-05-08

## 1. Synopsis

- **Purpose**: KnowledgeBase CLI commands for running the MCP server and validating wiki/handoff content.
- **I/O**: Shell command → MCP server process / lint report (exit 0 = pass, non-zero = fail).

## 2. Core Logic

### kb-mcp

MCP server. Exposes tools for ingest and other operations.

```bash
kb-mcp
```

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

## 3. Usage

Run the typical workflow in order:

```bash
# Step 1: Ingest sources
./scripts/ingest-github.sh owner/repo

# Step 2: Write wiki pages (LLM step, no command)

# Step 3: Validate wiki
kb-lint-wiki

# Step 4: Validate handoffs
kb-lint-handoff

# Step 5: Commit when both lints exit 0
cd data
git add raw/ wiki/ log.md
git commit -m "ingest: [source] description"
```

---

## Appendix

### A. Troubleshooting

**kb-lint-wiki errors on dead wikilink**
Fix the link or use plain text instead of a wikilink.

**kb-lint-wiki --check-immutability fails**
A raw file was modified. Revert the raw file to its original state.

**kb-lint-handoff fails on missing frontmatter field**
Add the missing field to the handoff document frontmatter.

**kb-mcp fails to start**
Check that `uv sync` was run and the entry point is on PATH.

### B. PatchNote

- 2026-05-08: Initial split from CLAUDE.md and restructured to follow docs/CLAUDE.md Standard Document Structure.
