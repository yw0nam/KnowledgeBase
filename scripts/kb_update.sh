#!/usr/bin/env bash
# kb_update.sh — deterministic kb_update pipeline.
#
# Replaces /kb_update SKILL orchestration with code-enforced steps.
# Only Step 3 (wiki page writing) calls the LLM; everything else is
# deterministic bash/git/lint with hard gates between steps.
#
# Pipeline:
#   1. detect new/changed raw files          (deterministic, git)
#   2. graph update                           (deterministic, graphify CLI)
#   3a. LLM writes entity pages (batched)     (LLM, isolated headless)
#   3b. LLM updates _index.md                 (LLM, isolated headless)
#   4. lint                                   (deterministic, HARD GATE)
#   5. append log.md                          (deterministic, bash)
#   6. commit                                 (deterministic, git)
#
# Run from anywhere — script cds to KnowledgeBase root.
#
# Env vars:
#   CLAUDE_BIN          claude CLI binary             (default: claude)
#   GRAPHIFY_CMD        graphify build command        (default: claude -p "/graphify data/raw/ --update --no-viz")
#   BATCH_SIZE          raw files per LLM batch       (default: 10)
#   MAX_LINT_RETRIES    lint fail → LLM fix attempts  (default: 3)
#   DRY_RUN=1           stop after step 1, no side effects
#
# Exit codes:
#   0  ok or no new files
#   1  lint failed (commit suppressed)
#   2  graph build failed
#   3  LLM step failed
#   4  repo / state error
#   5  prerequisite missing

set -euo pipefail

CLAUDE_BIN="${CLAUDE_BIN:-claude}"
GRAPHIFY_CMD="${GRAPHIFY_CMD:-$CLAUDE_BIN --dangerously-skip-permissions -p \"/graphify data/raw/ --update --no-viz\"}"
BATCH_SIZE="${BATCH_SIZE:-10}"
MAX_LINT_RETRIES="${MAX_LINT_RETRIES:-3}"
DRY_RUN="${DRY_RUN:-0}"

# ---- arg parsing ----
while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN=1 ;;
    -h|--help)
      sed -n '2,30p' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *) echo "kb_update: unknown arg: $1" >&2; exit 4 ;;
  esac
  shift
done

# ---- setup ----
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KB_ROOT="$(dirname "$SCRIPT_DIR")"
DATA_DIR="$KB_ROOT/data"
TODAY="$(date -u +%Y-%m-%d)"

cd "$KB_ROOT"

log()  { printf '[kb_update] %s\n' "$*" >&2; }
fail() { log "ERROR: $1"; exit "${2:-4}"; }

command -v "$CLAUDE_BIN" >/dev/null 2>&1 || fail "claude CLI not found ($CLAUDE_BIN)" 5
[ -d "$DATA_DIR/.git" ]                 || fail "data/ is not a git repo at $DATA_DIR" 4
[ -f scripts/lint-wiki.py ]             || fail "scripts/lint-wiki.py missing" 4

# =============================================================================
# Step 1 — detect new/changed raw files
# =============================================================================
log "Step 1: scanning data/raw/ for changes"

# Porcelain v1: first 2 chars are status. Take untracked (??) and any
# add/modify on .md files under raw/. Path is relative to data/.
mapfile -t RAW_CHANGES < <(
  git -C "$DATA_DIR" status --porcelain --untracked-files=all raw/ \
    | awk '{
        status=substr($0,1,2); path=substr($0,4)
        if (path ~ /\.md$/ && (status == "??" || status ~ /[MA]/)) print path
      }'
)

if [ "${#RAW_CHANGES[@]}" -eq 0 ]; then
  log "no new/changed raw files. nothing to do."
  exit 0
fi

log "found ${#RAW_CHANGES[@]} raw file(s):"
for f in "${RAW_CHANGES[@]}"; do log "  $f"; done

if [ "$DRY_RUN" = "1" ]; then
  log "DRY_RUN=1 — stopping before graph/LLM/commit"
  exit 0
fi

# =============================================================================
# Step 2 — graph update (deterministic, idempotent via SHA cache)
# =============================================================================
log "Step 2: graph update"
log "  cmd: $GRAPHIFY_CMD"

if ! ( cd "$KB_ROOT" && eval "$GRAPHIFY_CMD" ); then
  fail "graph build failed" 2
fi

[ -f "$DATA_DIR/graphify-out/graph.json" ] || fail "graph.json not produced after graphify run" 2

# =============================================================================
# Step 3a — LLM writes entity pages (batched)
# =============================================================================
log "Step 3a: LLM writes entity pages (batch_size=$BATCH_SIZE)"

ABS_RAW=()
for rel in "${RAW_CHANGES[@]}"; do
  ABS_RAW+=("$DATA_DIR/$rel")
done

# Prompt template — mirrors .claude/skills/kb_update/SKILL.md sub-agent block.
PROMPT_HEADER="You are a wiki writer for a personal knowledge base. You are running headless — do NOT invoke any skills, do NOT run /graphify, just execute the steps below directly.

Today's date: $TODAY
KnowledgeBase root: $KB_ROOT
Data directory: $DATA_DIR

## Your task

Process these raw files and write their wiki entity pages.

Raw files:"

PROMPT_FOOTER='## Steps

1. Read each raw file in the list above.
2. Read data/graphify-out/graph.json — for each file, find nodes and edges where source_file matches it. Use those relationships to populate the Relationships section.
3. For each file, create or update the wiki entity page:
   - New: data/wiki/entities/{subject}/{YYYY-MM}/PascalCase.md (derive subject from repo name or content)
   - Update: refresh `updated:` date, append to `sources:` if not already present
4. If a related concept page already exists in data/wiki/concepts/, update it. Do NOT create new concept pages.
5. Do NOT touch _index.md files (handled in a separate step).
6. Do NOT commit anything.
7. Report the exact file paths you created or updated.

## Frontmatter rules

- Dates quoted: `"2026-04-20"`
- Scalars unquoted: `type: entity` (not `type: "entity"`)
- Lists block style only: `sources:\n  - path` (not inline).
- `sources:` — only real existing raw file paths.
- Wikilinks: [[FileName]] or [[FileName|Display Text]] — no .md extension.
- Never link to pages that do not exist — use plain text instead.

## Entity page format

```markdown
---
type: entity
created: "YYYY-MM-DD"
updated: "YYYY-MM-DD"
sources:
  - raw/github/issues/repo_42.md
aliases: []
tags: []
---

# Page Title

## Overview
[1-2 paragraph summary from the raw source.]

## Key Details
[Technical details, implementation, architecture, etc.]

## Relationships
- [[RelatedPage|Related Page Title]] (relation type)
```'

total="${#ABS_RAW[@]}"
batch_total=$(( (total + BATCH_SIZE - 1) / BATCH_SIZE ))
batch_idx=0
for ((i=0; i<total; i+=BATCH_SIZE)); do
  batch_idx=$((batch_idx + 1))
  batch=("${ABS_RAW[@]:i:BATCH_SIZE}")
  log "  batch $batch_idx/$batch_total — ${#batch[@]} file(s)"

  files_block=""
  for p in "${batch[@]}"; do files_block+="$p"$'\n'; done

  prompt="$PROMPT_HEADER"$'\n'"$files_block"$'\n'"$PROMPT_FOOTER"

  if ! "$CLAUDE_BIN" --dangerously-skip-permissions -p "$prompt"; then
    fail "LLM batch $batch_idx failed (exited non-zero)" 3
  fi
done

# =============================================================================
# Step 3b — LLM updates _index.md for affected subjects
# =============================================================================
log "Step 3b: collecting affected subjects from wiki/entities/"

mapfile -t SUBJECTS < <(
  git -C "$DATA_DIR" status --porcelain wiki/entities/ \
    | awk '{ print substr($0,4) }' \
    | sed -nE 's|^wiki/entities/([^/]+)/.*$|\1|p' \
    | sort -u
)

if [ "${#SUBJECTS[@]}" -eq 0 ]; then
  log "  no entity changes detected — skipping _index update"
else
  log "  affected subjects: ${SUBJECTS[*]}"

  subjects_block=""
  for s in "${SUBJECTS[@]}"; do
    subjects_block+="data/wiki/entities/$s/"$'\n'
  done

  INDEX_PROMPT="You are running headless — do NOT invoke any skills.

Today's date: $TODAY
KnowledgeBase root: $KB_ROOT

## Your task

Update _index.md for each subject directory below. For each subject:
- If wiki/entities/{subject}/_index.md does not exist, create it.
- Add new entity pages under the appropriate \`### YYYY_MM\` section as wikilinks.
- Each link MUST have a one-line Korean description: \`- [[PascalCasePage|Page Title]] — 한 줄 설명\`.
- If a subject has 10+ pages in a month, group under \`#### Category\` sub-sections.
- Month headers use underscore (\`### 2026_04\`), not hyphen.
- Description rules: do NOT repeat the title; capture the actual change/decision; 15–35 chars.

Subjects to update:
$subjects_block

## Format reminder

\`\`\`markdown
---
type: entity
created: \"YYYY-MM-DD\"
updated: \"$TODAY\"
sources: []
aliases: []
tags:
  - project
---

# Subject Name

> [2-3줄 프로젝트 설명.]

## Pages

### YYYY_MM

- [[PascalCasePage|Page Title]] — 한 줄 설명
\`\`\`

Do NOT commit. Report which _index.md files you updated."

  if ! "$CLAUDE_BIN" --dangerously-skip-permissions -p "$INDEX_PROMPT"; then
    fail "LLM _index.md update failed" 3
  fi
fi

# =============================================================================
# Step 4 — LINT with LLM auto-fix loop (THE hard gate)
# =============================================================================
log "Step 4: lint (auto-fix loop, max=$MAX_LINT_RETRIES)"

LINT_LOG="$(mktemp)"
trap 'rm -f "$LINT_LOG"' EXIT

attempt=0
while :; do
  attempt=$((attempt + 1))
  log "  lint attempt $attempt/$MAX_LINT_RETRIES"

  if uv run python3 scripts/lint-wiki.py >"$LINT_LOG" 2>&1; then
    cat "$LINT_LOG" >&2
    log "lint PASSED on attempt $attempt"
    break
  fi

  cat "$LINT_LOG" >&2

  if [ "$attempt" -ge "$MAX_LINT_RETRIES" ]; then
    log "lint still FAILED after $attempt attempts — refusing to commit. fix manually and re-run."
    exit 1
  fi

  log "  asking LLM to fix lint errors"
  FIX_PROMPT="You are running headless — do NOT invoke any skills.

Today's date: $TODAY
KnowledgeBase root: $KB_ROOT

## Your task

The lint script reported errors in the wiki. Read the output below, identify each ERROR (ignore WARN), and fix the offending wiki page(s). Common ERROR types and fixes:

- Dead wikilinks → replace with plain text, or update to an existing target
- '.md' in wikilink target → remove the extension (use [[Name]] not [[Name.md]])
- LaTeX/HTML in body → rewrite as plain markdown
- Frontmatter format → match data/CLAUDE.md conventions (block-style lists, quoted dates, unquoted scalars)
- Stale sources → remove or repoint the sources: entry to a real raw file
- Missing frontmatter → add the required fields

Do NOT touch raw/ files (they are immutable).
Do NOT commit anything.
After fixing, just stop — the wrapper will re-run lint.

## Lint output

$(cat "$LINT_LOG")"

  if ! "$CLAUDE_BIN" --dangerously-skip-permissions -p "$FIX_PROMPT"; then
    fail "LLM lint-fix step failed" 3
  fi
done

# =============================================================================
# Step 5 — append log.md (deterministic, no LLM)
# =============================================================================
log "Step 5: appending log.md"

# Count wiki/ deltas.
created=0; updated=0
while IFS= read -r line; do
  status="${line:0:2}"; path="${line:3}"
  [[ "$path" == *.md ]] || continue
  case "$status" in
    "??"|"A "|"AM") created=$((created + 1)) ;;
    " M"|"M "|"MM") updated=$((updated + 1)) ;;
  esac
done < <(git -C "$DATA_DIR" status --porcelain --untracked-files=all wiki/)

# Concise sources hint: deepest raw subdir touched (e.g. "github/issues, manual").
# Falls back gracefully for shallow paths like raw/foo.md.
sources_hint=$(printf '%s\n' "${RAW_CHANGES[@]}" \
  | sed -nE -e 's|^raw/([^/]+/[^/]+)/.*|\1|p' -e 's|^raw/([^/]+)/[^/]+$|\1|p' \
  | sort -u | paste -sd ', ' -)
[ -z "$sources_hint" ] && sources_hint="raw"

{
  printf '\n## %s kb_update | %s\n\n' "$TODAY" "$sources_hint"
  printf -- '- New raw files: %s\n' "${#RAW_CHANGES[@]}"
  printf -- '- Created: %s pages, Updated: %s pages\n' "$created" "$updated"
  printf -- '- Lint: PASSED\n'
} >> "$DATA_DIR/log.md"

# =============================================================================
# Step 6 — commit
# =============================================================================
log "Step 6: commit"

git -C "$DATA_DIR" add raw/ wiki/ log.md

if git -C "$DATA_DIR" diff --cached --quiet; then
  log "  nothing staged — skipping commit"
else
  git -C "$DATA_DIR" commit -m "update: $sources_hint wiki synced"
  log "  committed: $(git -C "$DATA_DIR" rev-parse --short HEAD)"
fi

log "done."
