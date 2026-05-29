#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KB_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
TARGET_DATE="$(TZ=Asia/Seoul date -d 'yesterday' +%F)"
# While the AI session runs it writes to .cron/logs/ (not data/raw/) so the file
# is never in-flight inside the nested repo during the session's own git commit.
# After the session exits, the log is copied to data/raw/ops/cron/ and committed
# in a follow-up git commit so it lands in the data repo like all other cron logs.
INFLIGHT_LOG_DIR="$KB_ROOT/.cron/logs"
INFLIGHT_LOG="$INFLIGHT_LOG_DIR/cron-wrapup.log"
ARCHIVE_LOG_DIR="$KB_ROOT/data/raw/ops/cron/$(TZ=Asia/Seoul date -d "$TARGET_DATE" +%Y/%m)"

mkdir -p "$INFLIGHT_LOG_DIR"

PROMPT="Run the KB cron wrap-up for $TARGET_DATE. Import and follow .claude/skills/cron-wrapup/SKILL.md as the runtime contract. Import .claude/skills/handoff-document/SKILL.md for the run handoff. Do not read docs as runtime instructions. After successful data lint, commit only the nested data repo with message \"cron-wrapup: $TARGET_DATE\". Never commit the outer repo. Never push. If blocked, write the wrap-up with Status: FAILED and a handoff with status: ready, then exit non-zero."

if [ ! -d "$KB_ROOT/data/.git" ]; then
  echo "FATAL: $KB_ROOT/data/.git not found — run knowledgebase-initialize before cron." >> "$INFLIGHT_LOG"
  exit 1
fi

SYNC="$KB_ROOT/.claude/skills/data-sync/scripts/sync-data.sh"

# If the canonical sync lock is already held (manual sync, or a stuck prior run),
# flock -n below would silently skip the whole wrap-up. Probe first and leave a
# breadcrumb so the morning digest can see why the night produced no artefact.
if ! flock -n "$KB_ROOT/data/.git/kb-sync.lock" true 2>/dev/null; then
  echo "LOCK_CONTENDED: kb-sync.lock held by another process; cron-wrapup skipped for $TARGET_DATE" >> "$INFLIGHT_LOG"
  exit 1
fi

SESSION_EXIT=0
flock -n "$KB_ROOT/data/.git/kb-sync.lock" bash -c '
  set -uo pipefail   # -e omitted on purpose: the git-commit no-ops below use || true and would abort under -e
  KB_ROOT="$1"; PROMPT="$2"; TARGET_DATE="$3"; INFLIGHT_LOG="$4"
  ARCHIVE_LOG_DIR="$5"; ARCHIVE_REL="$6"; SYNC="$7"
  rc=0
  cd "$KB_ROOT"
  opencode run --model anthropic/claude-sonnet-4-6 --dangerously-skip-permissions \
    --dir "$KB_ROOT" "$PROMPT" >> "$INFLIGHT_LOG" 2>&1 || rc=$?

  # Archive + commit the run log on the work branch (post-session).
  mkdir -p "$ARCHIVE_LOG_DIR"
  cp "$INFLIGHT_LOG" "$ARCHIVE_LOG_DIR/$(basename "$ARCHIVE_REL")" \
    || echo "WARN: failed to archive run log to $ARCHIVE_LOG_DIR" >> "$INFLIGHT_LOG"
  git -C "$KB_ROOT/data" add "$ARCHIVE_REL" 2>/dev/null || true
  git -C "$KB_ROOT/data" diff --cached --quiet 2>/dev/null \
    || git -C "$KB_ROOT/data" commit -m "cron-wrapup-log: $TARGET_DATE" 2>/dev/null || true

  # Publish the day'\''s work as a PR (inside the same lock). Mark SYNC_SKIPPED in
  # the log if it cannot run, so the morning digest surfaces a silent machine.
  if [ -x "$SYNC" ]; then
    KB_SYNC_LOCKED=1 bash "$SYNC" >> "$INFLIGHT_LOG" 2>&1 \
      || echo "SYNC_SKIPPED: sync-data.sh exited non-zero" >> "$INFLIGHT_LOG"
  else
    echo "SYNC_SKIPPED: sync helper not found at $SYNC" >> "$INFLIGHT_LOG"
  fi
  exit $rc
' bash "$KB_ROOT" "$PROMPT" "$TARGET_DATE" "$INFLIGHT_LOG" "$ARCHIVE_LOG_DIR" \
  "raw/ops/cron/$(TZ=Asia/Seoul date -d "$TARGET_DATE" +%Y/%m)/${TARGET_DATE}_kb-cron-wrapup.log" \
  "$SYNC" || SESSION_EXIT=$?

exit $SESSION_EXIT
