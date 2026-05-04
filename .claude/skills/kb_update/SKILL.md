---
name: kb_update
description: KnowledgeBase incremental update skill. After new raw files are ingested, runs incremental graph update, writes wiki for new files only (parallel sub-agents), lint, log, and commit in sequence. Triggered when the user types `/kb_update` or requests "sync new files to wiki", "update wiki", "I ingested, now write wiki" etc.
---

# kb_update

After ingest, reflect newly added raw files into the wiki.
Incremental graph update → write wiki for new files only (parallel sub-agents) → lint → log → commit.


## Steps

### Step 1 — Identify changed files

```bash
uv run python -m kb_mcp.cli.diff_raw --mode all
```

This compares raw files on disk against:
- `graphify-out/manifest.json` (detects files not yet extracted into the graph)
- `wiki/` frontmatter sources (detects files without a wiki page)

If exit code is 1, output "No new files to process" and exit.
Capture the output (one path per line) as the list of new raw files for Step 3.

### Step 2 — Incremental graph update


/graphify raw/ --update --no-viz

### Step 2.5 — Generate skeletons (deterministic)

> **Generate the deterministic parts of wiki pages (frontmatter, sources, Relationships) via code.**
> The LLM only fills in the body (title, Overview, Key Details) in Step 3.

For each new/changed raw file from Step 1, generate a skeleton into a temp directory:

```bash
SKELETON_DIR=$(mktemp -d)
# Clean up on exit
trap 'rm -rf "$SKELETON_DIR"' EXIT

for rel in <raw file list from Step 1>; do
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

The `$SKELETON_DIR` path is passed to sub-agent prompts in Step 3.

### Step 3 — Wiki update (parallel sub-agents)

> **To save context, dispatch a sub-agent per file batch.**
> The main agent handles orchestration and `_index.md` updates only.

#### 3-1. Parallel sub-agent dispatch

Batch new/changed raw files from Step 1 into groups of **up to 10 files** and dispatch via the Agent tool.
≤10 files → 1 sub-agent, 11-20 → 2 sub-agents, etc. (ceiling division).
Independent batches are dispatched **simultaneously as multiple Agent tool calls in one message**.

Sub-agent prompt template (fill with actual values):

```
You are a wiki writer for a personal knowledge base. You are a subagent — do NOT use any skills, do NOT invoke graphify, just follow these instructions directly.

Today's date: {YYYY-MM-DD}
KnowledgeBase root: ./
Skeleton directory: {SKELETON_DIR}   # temp dir created in Step 2.5

## Your task

Process these raw files. Each file already has a deterministic skeleton at
`{SKELETON_DIR}/{basename}.skeleton.md` with frontmatter and Relationships
pre-populated. Your job is to fill in the title, Overview, and Key Details only.

Raw files:
{absolute_raw_file_path_1}
{absolute_raw_file_path_2}
...
(up to 10 files)

## Steps

1. Read each raw file in the list above.
2. Read the corresponding skeleton at `{SKELETON_DIR}/{basename}.skeleton.md`
   where `{basename}` is the raw filename without `.md`.
3. Determine the final wiki path:
   - subject: derive from repo name or content (e.g. `nanobot_runtime`)
   - YYYY-MM: from raw frontmatter `captured_at` or `created_at`
   - PascalCase: from the title you'll write
   - Path: `wiki/entities/{subject}/{YYYY-MM}/PascalCase.md`
4. Take the skeleton content and modify ONLY these placeholders:
   - Replace `# <!-- LLM TODO: title -->` with `# Actual Title` (one H1 line)
   - Replace the `## Overview` placeholder with a 1-2 paragraph summary
   - Replace the `## Key Details` placeholder with technical details
5. Save the result to the path from step 3.
6. **HARD RULES — DO NOT VIOLATE**:
   - DO NOT modify the frontmatter `created`, `updated`, `sources` fields
   - DO NOT modify the `## Relationships` section (heading or any line under it)
   - DO NOT add commentary, links, or sections that aren't in the skeleton
   - You MAY add tags to `tags: []` if clearly appropriate from the raw content
7. **Update path** (file already exists at the wiki path): refresh
   `updated:` to today's date, append the raw file path to `sources:` if not
   already present, then re-fill Overview/Key Details. Leave Relationships
   from the skeleton (it reflects the latest graph).
8. If a related concept page already exists in `wiki/concepts/`, update
   it. Do NOT create new concept pages.
9. Do NOT touch `_index.md` files (handled in Step 3-2).
10. Do NOT commit anything.
11. Report the exact file paths you created or updated.

## Frontmatter rules (for reference — already correct in the skeleton)

- Dates quoted: `"2026-04-20"`
- Scalars unquoted: `type: entity`
- Lists block style only: `sources:\n  - path`
- Wikilinks: `[[FileName]]` or `[[FileName|Display Text]]` — no `.md` extension
- Never link to pages that do not exist — use plain text instead
```

#### 3-2. _index.md update

After all sub-agents complete, the main agent updates each affected subject's `_index.md`.

- Create `wiki/entities/{subject}/_index.md` if it doesn't exist
- Add new entity pages as wikilinks under the appropriate section
- **Each link must have a one-line description** (`— description` format)
- Subjects with 10+ pages get functional area sections
- Format:

```markdown
---
type: entity
created: "YYYY-MM-DD"
updated: "YYYY-MM-DD"
sources: []
aliases: []
tags:
  - project
---

# Subject Name

> [2-3 line project/topic description. What it covers, core tech/scope.]

## Pages

### YYYY_MM

#### Category Name (functional grouping when 10+ pages)

- [[PascalCasePage|Page Title]] — one-line description of this page's key content

### YYYY_MM (no categories when <10 pages)

- [[PascalCasePage|Page Title]] — one-line description of this page's key content
```

**Structure rules:**
- Month headers always use `### YYYY_MM` (underscore, not hyphen)
- 10+ pages: group by `#### Category` under each month
- <10 pages: list links directly under month header without categories

**One-line description rules:**
- Do not repeat the title ("PR11 TTS Pipeline — TTS pipeline" ❌)
- Describe actual changes or key decisions ("Added POST /v1/tts/speak endpoint" ✅)
- Keep to 15-35 characters

### Step 4 — Lint

```bash
uv run python3 scripts/lint-wiki.py
```

If ERRORs exist, fix and re-run. Proceed only after PASSED.

### Step 5 — Log

Append to `log.md`:

```markdown
## {YYYY-MM-DD} kb_update | {summary of processed sources}

- New raw files: N
- Created: X pages, Updated: Y pages
- Lint: PASSED
```

### Step 6 — Commit

```bash
git add raw/ wiki/ log.md && git commit -m "update: {source name} wiki synced"
```
