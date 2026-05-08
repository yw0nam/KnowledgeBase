# Pipeline

Updated: 2026-05-08

## 1. Synopsis

- **Purpose**: 4-stage pipeline that turns raw sources into validated wiki pages.
- **I/O**: Files in `data/raw/` → wiki pages in `data/wiki/` + lint pass.

## 2. Core Logic

```
1. INGEST → 2. FILL → 3. LOG → 4. LINT
(script)    (LLM)    (LLM)   (script)
```

### Stage 1: Ingest

Collect raw sources into `data/raw/`.

```bash
./scripts/ingest-github.sh owner/repo    # GitHub CLAUDE.md + Issues + PRs
# Or drop files manually into data/raw/manual/
```

Result: markdown files with frontmatter in `data/raw/{type}/`.

### Stage 2: Fill

Read raw files and create or update wiki pages in `data/wiki/`.

- Identify unprocessed raw files
- Read each raw file
- Create or update the relevant wiki page
- Ensure `sources:` in frontmatter references actual raw file paths
- Only use wikilinks to pages that exist

### Stage 3: Log

Append to `data/log.md` after wiki changes. Include:
- What was ingested
- Which wiki pages were created/updated
- Any decisions or issues encountered

### Stage 4: Lint

Validate wiki pages and handoff documents.

```bash
kb-lint-wiki                      # errors only = fail
kb-lint-wiki --strict             # warnings also = fail
kb-lint-handoff                   # validate handoffs
```

## 3. Usage

**Happy Path:** One cycle from source collection through validation.

1. Ingest GitHub sources:
```bash
./scripts/ingest-github.sh owner/repo
```

2. Review raw files in `data/raw/github/` and `data/raw/issues/`.

3. Write wiki pages to `data/wiki/` based on raw content.

4. Log the operation:
```bash
# Append to data/log.md
# - Ingested: owner/repo CLAUDE.md + 5 issues
# - Updated: wiki/entities/ProjectName/2026-05/
# - Notes: Extracted architecture decisions
```

5. Validate:
```bash
kb-lint-wiki
```

6. Commit to nested repo:
```bash
cd data
git add raw/ wiki/ log.md
git commit -m "ingest: owner/repo description"
```

---

## Appendix

### A. Troubleshooting

**ERROR checks (cannot commit):**
- Dead wikilinks: Target page does not exist
- `.md` in target: Wikilink includes file extension
- LaTeX/HTML: Unsupported markup in wiki pages
- Frontmatter format: Invalid YAML or missing required fields
- Stale sources: `captured_at` timestamp is too old
- Missing frontmatter: Required fields absent from raw or wiki files

**WARN checks (informational):**
- Self-links: Page links to itself
- Unfilled placeholders: `[TODO]` or `[FILL]` markers remain
- Orphan pages: No incoming wikilinks from other pages
- Empty sections: Heading with no content below

### B. PatchNote

- 2026-05-08: Initial split from CLAUDE.md and restructured to follow docs/CLAUDE.md Standard Document Structure. Preserved all 4 stages, bash commands, and lint check categories.
