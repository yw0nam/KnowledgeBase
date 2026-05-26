#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KB_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
LOG_DIR="$KB_ROOT/.cron/logs"
LOCK_DIR="$KB_ROOT/.cron/locks"
TARGET_DATE="$(TZ=Asia/Seoul date -d 'yesterday' +%F)"
# kb-cron-wrapup's own log stays under .cron/logs/ (not data/raw/) because the file
# is still being written during the wrap-up's own git commit step, which would
# otherwise risk staging an in-flight file or tripping raw immutability on next run.
LOG_FILE="$LOG_DIR/cron-wrapup.log"

mkdir -p "$LOG_DIR" "$LOCK_DIR"

PROMPT="Run the KB cron wrap-up for $TARGET_DATE. Import and follow .claude/skills/cron-wrapup/SKILL.md as the runtime contract. Import .claude/skills/handoff-document/SKILL.md for the run handoff. Do not read docs as runtime instructions. After successful data lint, commit only the nested data repo with message \"cron-wrapup: $TARGET_DATE\". Never commit the outer repo. Never push. If blocked, write the wrap-up with Status: FAILED and a handoff with status: ready, then exit non-zero."

flock -n "$LOCK_DIR/cron-wrapup.lock" bash -c '
  cd "$1"
  opencode run \
    --model anthropic/claude-sonnet-4-6 \
    --dangerously-skip-permissions \
    --dir "$1" \
    "$2"
' bash "$KB_ROOT" "$PROMPT" >> "$LOG_FILE" 2>&1
