---
name: kb_init
description: KnowledgeBase initial setup skill. After placing raw sources for the first time, runs full graph build, writes all wiki pages, lint, log, and commit in sequence. Triggered when the user types `/kb_init` or requests "set up KnowledgeBase", "create wiki from scratch", "initialize" etc.
---

# kb_init

KnowledgeBase initial setup. Run once after placing raw sources for the first time.
Graph build → write all wiki pages → lint → log → commit.

## Steps

### Step 1 — Verify structure

Create directories if they don't exist:

```bash
cp -r templates/ .
```

```bash
mkdir -p raw/github/claude-md raw/github/issues raw/manual
mkdir -p wiki/entities wiki/concepts wiki/summaries wiki/decisions wiki/questions
touch log.md 2>/dev/null || true
```

### Step 2 — Graph build

/graphify raw/ --no-viz

### Step 2.5 — Generate all skeletons (deterministic)

> **Generate the deterministic parts of all entity pages (frontmatter, sources, Relationships) via code.**
> In Step 3, the LLM only fills in the body (title, Overview, Key Details).

Iterate over all files in `raw/` and generate skeletons into a temp directory:

```bash
SKELETON_DIR=$(mktemp -d)
trap 'rm -rf "$SKELETON_DIR"' EXIT

# Generate skeleton for every .md file in raw/
find raw -type f -name "*.md" -print0 \
  | while IFS= read -r -d '' abs_path; do
      rel="$abs_path"
      basename=$(basename "$rel" .md)
      uv run python -m kb_mcp.cli.skeleton_gen \
        "$rel" \
        "graphify-out/graph.json" \
        "wiki" \
        > "$SKELETON_DIR/${basename}.skeleton.md"
    done
```

What the skeleton fills deterministically:

- **frontmatter**: `type: entity`, `created`/`updated` (today's date, quoted), `sources` (raw file path), `aliases: []`, `tags: []`
- **`## Relationships`**: extracts outgoing edges from `graph.json` where `source_file` matches the raw file, formatted as `[[FileName|Label]] (relation)`. If no matching wiki page exists, uses plain text + `<!-- no wiki page yet -->` comment.

Placeholders for LLM to fill:

- `# <!-- LLM TODO: title -->`
- `## Overview` body
- `## Key Details` body

The `$SKELETON_DIR` path is referenced in Step 3.

### Step 3 — Write all wiki pages

> **Always read `references/wiki_templates.md` first before starting.**
> All wiki pages must follow those templates exactly.

#### 3-1. Entity pages (skeleton-based)

For each raw file:

1. Read the raw file (`raw/{type}/{file}.md`)
2. Read the corresponding skeleton (`$SKELETON_DIR/{basename}.skeleton.md`)
3. Determine the final wiki path:
   - subject: repo name from the raw file (e.g. `DesktopMatePlus`) or topic
   - `{YYYY-MM}`: extracted from raw frontmatter `created_at` or `captured_at`
   - PascalCase: derived from the title to be written
   - Path: `wiki/entities/{subject}/{YYYY-MM}/PascalCase.md`
4. Take skeleton content and replace only these placeholders:
   - `# <!-- LLM TODO: title -->` → `# Actual Title`
   - `## Overview` placeholder → 1-2 paragraph summary
   - `## Key Details` placeholder → technical details
5. Save to the path from step 3.
6. **HARD RULES**:
   - NEVER modify frontmatter `created`, `updated`, `sources`
   - NEVER modify the `## Relationships` section (heading + body)
   - Adding tags to `tags: []` based on raw content is OK

#### 3-2. Concept pages (no skeleton — write directly)

Identify hyperedges in `graphify-out/graph.json` or common patterns spanning multiple entities.

- Location: `wiki/concepts/Snake_Case.md`
- Follow the Concept page template from `references/wiki_templates.md` exactly.
- No skeleton is used since there's no 1:1 raw mapping.

#### 3-3. Subject hub `_index.md` (no skeleton — write directly)

Create `wiki/entities/{subject}/_index.md` for each subject directory.

- List all entity pages under that subject
- Required: blockquote description (> ...) at the top
- Each link must have a one-line description (`— description` format)
- Month headers use `### YYYY_MM` (underscore, not hyphen)
- 10+ pages: group by `#### Category` under each month
- <10 pages: list links directly under month header without categories
- One-line descriptions must not repeat the title; describe actual changes/key decisions in 15-35 characters

### Step 4 — Lint

```bash
uv run python3 scripts/lint-wiki.py
```

If ERRORs exist, fix and re-run. Proceed only after PASSED.

### Step 5 — Log

Append to `log.md`:

```markdown
## {YYYY-MM-DD} kb_init | {summary of processed sources}

- Processed N raw files
- Created X wiki pages (entities: N, concepts: N)
- Lint: PASSED
```

### Step 6 — Commit

```bash
git add raw/ wiki/ log.md && git commit -m "init: KnowledgeBase wiki generated"
```
