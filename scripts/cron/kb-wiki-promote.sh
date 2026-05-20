#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KB_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
LOG_DIR="$KB_ROOT/.cron/logs"
LOCK_DIR="$KB_ROOT/.cron/locks"
TARGET_DATE="$(TZ=Asia/Seoul date -d 'yesterday' +%F)"

mkdir -p "$LOG_DIR" "$LOCK_DIR"

flock -n "$LOCK_DIR/wiki-promote.lock" bash -lc "
  cd '$KB_ROOT'
  opencode run \
    --model anthropic/claude-sonnet-4-6 \
    --dangerously-skip-permissions \
    --dir '$KB_ROOT' \
    'Run the KnowledgeBase wiki promotion workflow for $TARGET_DATE. Read docs/workflows/wiki-approval-workflow.md first for the Daily-update agent contract and promotion criteria. Step 1: run git -C data status --short to find uncommitted wiki pages from the recent daily build. Step 2: run uv run kb-wiki-review list --status not_processed to list all candidate pages. Step 3: prioritize newly uncommitted pages, then any older not_processed pages still awaiting judgment. Step 4: for each candidate, apply the three promotion criteria — clear verifiable source, future lookup value, knowledge not event dump. Step 5: promote worthy pages with uv run kb-wiki-review promote <stem>. Do NOT reject any page; only users reject. Leave borderline pages for TTL. Step 6: write a handoff under data/handoffs/YYYY/MM/wiki-promote/ and append data/log.md with promoted stems and skipped stems. Step 7: if any pages were promoted, commit the nested data/ repo with message: promote: YYYY-MM-DD wiki promotion. Do not push to remote.'
" >> "$LOG_DIR/wiki-promote.log" 2>&1
