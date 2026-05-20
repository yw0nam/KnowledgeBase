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
    'Run the KnowledgeBase daily memory workflow for $TARGET_DATE. Read docs/workflows/periodic-memory-workflow.md first. Read docs/workflows/cron-jobs.md before executing shell commands. Use data/handoffs as the operational state board. Never edit existing data/raw files. Run required lint commands. Do not run git commit, git push, or any other VCS write operation; leave validated changes uncommitted for manual review. If blocked, write a handoff and append data/log.md before exiting.'
" >> "$LOG_DIR/daily.log" 2>&1
