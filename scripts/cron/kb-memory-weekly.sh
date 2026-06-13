#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KB_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
source "$SCRIPT_DIR/_db.sh"
LOCK_DIR="$KB_ROOT/.cron/locks"
TARGET_WEEK="$(TZ=Asia/Seoul date -d 'last week' +%G-W%V)"
TARGET_DATE="$(TZ=Asia/Seoul date -d 'yesterday' +%F)"
LOG_DIR="$KB_ROOT/data/raw/ops/cron/$(TZ=Asia/Seoul date -d "$TARGET_DATE" +%Y/%m)"
LOG_FILE="$LOG_DIR/${TARGET_DATE}_kb-memory-weekly.log"

mkdir -p "$LOG_DIR" "$LOCK_DIR"

RUN_EXIT=0
flock -n "$LOCK_DIR/weekly.lock" bash -c "
  cd '$KB_ROOT'
  "$OPENCODE_BIN" run \
    --model "$KB_OPENCODE_MODEL" \
    --dangerously-skip-permissions \
    --dir '$KB_ROOT' \
    'Run the weekly memory workflow for $TARGET_WEEK. Import and follow .claude/skills/memory-report/SKILL.md §Weekly as the runtime contract. Import .claude/skills/wiki-authoring/SKILL.md for any wiki page edits and .claude/skills/handoff-document/SKILL.md for the handoff. Do not read docs as runtime instructions. Read canonical state from Postgres and write durable state through the kb-mcp tools only. Do not run git or edit data/ as source of truth. If blocked, write a handoff with status: ready and submit an operation log through the kb-mcp create_operation_log tool before exiting.'
" >> "$LOG_FILE" 2>&1 || RUN_EXIT=$?
kb_finish_cron_run "kb-memory-weekly" "$TARGET_WEEK" "$RUN_EXIT" "$LOG_FILE"
exit $?
