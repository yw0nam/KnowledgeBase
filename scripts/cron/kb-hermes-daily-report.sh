#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KB_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
LOCK_DIR="$KB_ROOT/.cron/locks"
TARGET_DATE="$(TZ=Asia/Seoul date -d 'yesterday' +%F)"
LOG_DIR="$KB_ROOT/data/raw/ops/cron/$(TZ=Asia/Seoul date -d "$TARGET_DATE" +%Y/%m)"
LOG_FILE="$LOG_DIR/${TARGET_DATE}_kb-hermes-daily-report.log"

mkdir -p "$LOG_DIR" "$LOCK_DIR"

if ! flock -n "$LOCK_DIR/hermes-report.lock" \
    bash -lc "
      cd '$KB_ROOT'
      uv run kb-hermes-daily-report --date '$TARGET_DATE' --lint
    " >> "$LOG_FILE" 2>&1; then
  echo "[$(date -Iseconds)] ERROR: kb-hermes-daily-report failed for $TARGET_DATE" >&2
  exit 1
fi
