#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KB_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
LOCK_DIR="$KB_ROOT/.cron/locks"
TARGET_DATE="$(TZ=Asia/Seoul date -d 'yesterday' +%F)"
# While the AI session runs it writes to .cron/logs/ (not data/raw/) so the file
# is never in-flight inside the nested repo during the session's own git commit.
# After the session exits, the log is copied to data/raw/ops/cron/ and committed
# in a follow-up git commit so it lands in the data repo like all other cron logs.
INFLIGHT_LOG_DIR="$KB_ROOT/.cron/logs"
INFLIGHT_LOG="$INFLIGHT_LOG_DIR/cron-wrapup.log"
ARCHIVE_LOG_DIR="$KB_ROOT/data/raw/ops/cron/$(TZ=Asia/Seoul date -d "$TARGET_DATE" +%Y/%m)"
ARCHIVE_LOG="$ARCHIVE_LOG_DIR/${TARGET_DATE}_kb-cron-wrapup.log"

mkdir -p "$INFLIGHT_LOG_DIR" "$LOCK_DIR"

PROMPT="Run the KB cron wrap-up for $TARGET_DATE. Import and follow .claude/skills/cron-wrapup/SKILL.md as the runtime contract. Import .claude/skills/handoff-document/SKILL.md for the run handoff. Do not read docs as runtime instructions. After successful data lint, commit only the nested data repo with message \"cron-wrapup: $TARGET_DATE\". Never commit the outer repo. Never push. If blocked, write the wrap-up with Status: FAILED and a handoff with status: ready, then exit non-zero."

SESSION_EXIT=0
flock -n "$LOCK_DIR/cron-wrapup.lock" bash -c '
  cd "$1"
  opencode run \
    --model anthropic/claude-sonnet-4-6 \
    --dangerously-skip-permissions \
    --dir "$1" \
    "$2"
' bash "$KB_ROOT" "$PROMPT" >> "$INFLIGHT_LOG" 2>&1 || SESSION_EXIT=$?

# Archive the completed log to data/ now that the session and its git commit are done.
# This runs regardless of session exit code — partial logs are useful for debugging.
mkdir -p "$ARCHIVE_LOG_DIR"
cp "$INFLIGHT_LOG" "$ARCHIVE_LOG"
git -C "$KB_ROOT/data" add \
  "raw/ops/cron/$(TZ=Asia/Seoul date -d "$TARGET_DATE" +%Y/%m)/${TARGET_DATE}_kb-cron-wrapup.log" \
  2>/dev/null || true
git -C "$KB_ROOT/data" diff --cached --quiet 2>/dev/null || \
  git -C "$KB_ROOT/data" commit -m "cron-wrapup-log: $TARGET_DATE" 2>/dev/null || true

exit $SESSION_EXIT
