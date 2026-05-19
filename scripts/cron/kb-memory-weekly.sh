#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KB_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
LOG_DIR="$KB_ROOT/.cron/logs"
LOCK_DIR="$KB_ROOT/.cron/locks"
TARGET_WEEK="$(TZ=Asia/Seoul date -d 'last week' +%G-W%V)"

mkdir -p "$LOG_DIR" "$LOCK_DIR"

flock -n "$LOCK_DIR/weekly.lock" bash -lc "
  cd '$KB_ROOT'
  opencode run \
    --model anthropic/claude-sonnet-4-6 \
    --dangerously-skip-permissions \
    --dir '$KB_ROOT' \
    'Run the KnowledgeBase weekly memory workflow for $TARGET_WEEK. Read docs/workflows/periodic-memory-workflow.md first. Read docs/workflows/cron-jobs.md before executing shell commands. Use data/handoffs as the operational state board. Never edit existing data/raw files. Run required lint commands. Commit the nested data repo only if lint passes. If blocked, write a handoff and append data/log.md before exiting.'
" >> "$LOG_DIR/weekly.log" 2>&1
