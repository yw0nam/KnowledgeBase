#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KB_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
LOG_DIR="$KB_ROOT/.cron/logs"
LOCK_DIR="$KB_ROOT/.cron/locks"
TARGET_DATE="$(TZ=Asia/Seoul date -d 'yesterday' +%F)"

mkdir -p "$LOG_DIR" "$LOCK_DIR"

if ! flock -n "$LOCK_DIR/claude-code-report.lock" \
    bash -lc "
      cd '$KB_ROOT'
      uv run kb-claude-code-daily-report --date '$TARGET_DATE' --lint
    " >> "$LOG_DIR/claude-code-report.log" 2>&1; then
  echo "[$(date -Iseconds)] ERROR: kb-claude-code-daily-report failed for $TARGET_DATE" >&2
  exit 1
fi
