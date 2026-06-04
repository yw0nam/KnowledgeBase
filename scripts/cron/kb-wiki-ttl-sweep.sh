#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KB_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
source "$SCRIPT_DIR/_db.sh"
LOCK_DIR="$KB_ROOT/.cron/locks"
TARGET_DATE="$(TZ=Asia/Seoul date -d 'yesterday' +%F)"
LOG_DIR="$KB_ROOT/data/raw/ops/cron/$(TZ=Asia/Seoul date -d "$TARGET_DATE" +%Y/%m)"
LOG_FILE="$LOG_DIR/${TARGET_DATE}_kb-wiki-ttl-sweep.log"

mkdir -p "$LOG_DIR" "$LOCK_DIR"

RUN_EXIT=0
flock -n "$LOCK_DIR/wiki-ttl-sweep.lock" \
    bash -lc "cd '$KB_ROOT' && uv run kb-db-ttl-sweep --days 7" \
    >> "$LOG_FILE" 2>&1 || RUN_EXIT=$?
if [[ "$RUN_EXIT" -ne 0 ]]; then
  echo "[$(date -Iseconds)] ERROR: kb-wiki-ttl-sweep failed" >&2
fi
kb_finish_cron_run "kb-wiki-ttl-sweep" "$TARGET_DATE" "$RUN_EXIT" "$LOG_FILE"
exit $?
