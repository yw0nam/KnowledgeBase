#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KB_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
LOG_DIR="$KB_ROOT/.cron/logs"
LOCK_DIR="$KB_ROOT/.cron/locks"
TARGET_DATE="$(TZ=Asia/Seoul date -d 'yesterday' +%F)"

mkdir -p "$LOG_DIR" "$LOCK_DIR"

flock -n "$LOCK_DIR/daily.lock" bash -lc "
  cd '$KB_ROOT'
  opencode run \
    --model anthropic/claude-sonnet-4-6 \
    --dangerously-skip-permissions \
    --dir '$KB_ROOT' \
    'Run the daily memory workflow for $TARGET_DATE. Import and follow .claude/skills/memory-report/SKILL.md §Daily as the runtime contract. Import .claude/skills/wiki-authoring/SKILL.md for any wiki page edits and .claude/skills/handoff-document/SKILL.md for the handoff. Do not read docs as runtime instructions. Never run git commit. If blocked, write a handoff with status: ready and append data/log.md before exiting.'
" >> "$LOG_DIR/daily.log" 2>&1
