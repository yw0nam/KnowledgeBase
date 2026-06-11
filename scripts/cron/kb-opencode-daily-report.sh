#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KB_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
source "$SCRIPT_DIR/_db.sh"
LOCK_DIR="$KB_ROOT/.cron/locks"
TARGET_DATE="$(TZ=Asia/Seoul date -d 'yesterday' +%F)"
LOG_DIR="$KB_ROOT/data/raw/ops/cron/$(TZ=Asia/Seoul date -d "$TARGET_DATE" +%Y/%m)"
LOG_FILE="$LOG_DIR/${TARGET_DATE}_kb-opencode-daily-report.log"

mkdir -p "$LOG_DIR" "$LOCK_DIR"

RUN_EXIT=0
flock -n "$LOCK_DIR/opencode-report.lock" \
    bash -c '
      cd "$1"
      env -u VIRTUAL_ENV "$UV_BIN" run kb-opencode-daily-report --date "$2" --lint
    ' bash "$KB_ROOT" "$TARGET_DATE" >> "$LOG_FILE" 2>&1 || RUN_EXIT=$?
if [[ "$RUN_EXIT" -ne 0 ]]; then
  echo "[$(date -Iseconds)] ERROR: kb-opencode-daily-report failed for $TARGET_DATE" >&2
fi
kb_finish_cron_run "kb-opencode-daily-report" "$TARGET_DATE" "$RUN_EXIT" "$LOG_FILE"
exit $?
