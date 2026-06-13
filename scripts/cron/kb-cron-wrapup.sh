#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KB_ROOT="${KB_ROOT_OVERRIDE:-$(cd "$SCRIPT_DIR/../.." && pwd)}"
source "$SCRIPT_DIR/_db.sh"
TARGET_DATE="$(TZ=Asia/Seoul date -d 'yesterday' +%F)"
INFLIGHT_LOG_DIR="$KB_ROOT/.cron/logs"
INFLIGHT_LOG="$INFLIGHT_LOG_DIR/cron-wrapup.log"
ARCHIVE_LOG_DIR="$KB_ROOT/data/raw/ops/cron/$(TZ=Asia/Seoul date -d "$TARGET_DATE" +%Y/%m)"
LOCK_DIR="$KB_ROOT/.cron/locks"

mkdir -p "$INFLIGHT_LOG_DIR" "$LOCK_DIR"

PROMPT="Run the KB cron wrap-up for $TARGET_DATE. Import and follow .claude/skills/cron-wrapup/SKILL.md as the runtime contract. Import .claude/skills/handoff-document/SKILL.md for the run handoff. Do not read docs as runtime instructions. Write all durable state through the kb-mcp tools. Do not run git, do not commit data/, and do not push. If blocked, write the wrap-up with Status: FAILED and a handoff with status: ready, then exit non-zero."

SESSION_EXIT=0
ARCHIVE_LOG="$ARCHIVE_LOG_DIR/${TARGET_DATE}_kb-cron-wrapup.log"
flock -n "$LOCK_DIR/cron-wrapup.lock" bash -c '
  set -uo pipefail
  KB_ROOT="$1"; PROMPT="$2"; TARGET_DATE="$3"; INFLIGHT_LOG="$4"
  ARCHIVE_LOG_DIR="$5"; ARCHIVE_LOG="$6"
  rc=0
  cd "$KB_ROOT"
  "$OPENCODE_BIN" run --model "$KB_OPENCODE_MODEL" --dangerously-skip-permissions \
    --dir "$KB_ROOT" "$PROMPT" >> "$INFLIGHT_LOG" 2>&1 || rc=$?

  # Archive the completed run log as generated export evidence; DB is canonical.
  archive_rc=0
  mkdir -p "$ARCHIVE_LOG_DIR" || archive_rc=$?
  [ "$archive_rc" -ne 0 ] \
    || cp "$INFLIGHT_LOG" "$ARCHIVE_LOG" || archive_rc=$?
  [ "$archive_rc" -eq 0 ] \
    || echo "WARN: failed to archive run log to $ARCHIVE_LOG_DIR (rc=$archive_rc)" >> "$INFLIGHT_LOG"

  [ "$rc" -ne 0 ] || [ "$archive_rc" -eq 0 ] || rc=$archive_rc
  exit $rc
' bash "$KB_ROOT" "$PROMPT" "$TARGET_DATE" "$INFLIGHT_LOG" "$ARCHIVE_LOG_DIR" "$ARCHIVE_LOG" \
  || SESSION_EXIT=$?

if [[ ! -f "$ARCHIVE_LOG" ]]; then
  ARCHIVE_LOG="$INFLIGHT_LOG"
fi
kb_finish_cron_run "kb-cron-wrapup" "$TARGET_DATE" "$SESSION_EXIT" "$ARCHIVE_LOG"
exit $?
