#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KB_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
LOCK_DIR="$KB_ROOT/.cron/locks"
TARGET_WEEK="$(TZ=Asia/Seoul date -d 'last week' +%G-W%V)"
TARGET_DATE="$(TZ=Asia/Seoul date -d 'yesterday' +%F)"
LOG_DIR="$KB_ROOT/data/raw/ops/cron/$(TZ=Asia/Seoul date -d "$TARGET_DATE" +%Y/%m)"
LOG_FILE="$LOG_DIR/${TARGET_DATE}_kb-memory-weekly.log"

mkdir -p "$LOG_DIR" "$LOCK_DIR"

flock -n "$LOCK_DIR/weekly.lock" bash -lc "
  cd '$KB_ROOT'
  opencode run \
    --model anthropic/claude-sonnet-4-6 \
    --dangerously-skip-permissions \
    --dir '$KB_ROOT' \
    'Run the weekly memory workflow for $TARGET_WEEK. Import and follow .claude/skills/memory-report/SKILL.md §Weekly as the runtime contract. Import .claude/skills/wiki-authoring/SKILL.md for any wiki page edits and .claude/skills/handoff-document/SKILL.md for the handoff. Do not read docs as runtime instructions. Never run git commit. If blocked, write a handoff with status: ready and append data/log.md before exiting.'
" >> "$LOG_FILE" 2>&1
