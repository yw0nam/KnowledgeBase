#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KB_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
source "$SCRIPT_DIR/_db.sh"
LOCK_DIR="$KB_ROOT/.cron/locks"
TARGET_DATE="$(TZ=Asia/Seoul date -d 'yesterday' +%F)"
LOG_DIR="$KB_ROOT/data/raw/ops/cron/$(TZ=Asia/Seoul date -d "$TARGET_DATE" +%Y/%m)"
LOG_FILE="$LOG_DIR/${TARGET_DATE}_kb-wiki-promote.log"

mkdir -p "$LOG_DIR" "$LOCK_DIR"

RUN_EXIT=0
{
  echo "[$(TZ=Asia/Seoul date --iso-8601=seconds)] kb-wiki-promote start target=$TARGET_DATE"

  set +e
  flock -n "$LOCK_DIR/wiki-promote.lock" bash -lc "
    cd '$KB_ROOT'
    env -u VIRTUAL_ENV timeout --kill-after=30s 540s opencode run \
      --model anthropic/claude-sonnet-4-6 \
      --dangerously-skip-permissions \
      --dir '$KB_ROOT' \
      'Run the KnowledgeBase wiki promotion workflow for $TARGET_DATE. Import and follow .claude/skills/wiki-approval/SKILL.md as the runtime contract. Import .claude/skills/wiki-authoring/SKILL.md only if page metadata/content fixes are needed before promotion. Do not read docs as runtime instructions. Promote worthy not_processed pages through the DB API, leave borderline pages for TTL, write the wiki-promote handoff and operation log through the DB API. Do not run git, commit data/, or push.'
  "
  status=$?
  set -e

  if [[ $status -ne 0 ]]; then
    echo "[$(TZ=Asia/Seoul date --iso-8601=seconds)] kb-wiki-promote failed status=$status"
    if [[ $status -eq 1 ]]; then
      echo "lock busy: another wiki-promote process is still holding $LOCK_DIR/wiki-promote.lock"
      fuser -v "$LOCK_DIR/wiki-promote.lock" || true
    elif [[ $status -eq 124 ]]; then
      echo "opencode timed out after 540s; timeout should have terminated the child before Hermes cron's 600s script limit"
    fi
    RUN_EXIT="$status"
  else
    echo "[$(TZ=Asia/Seoul date --iso-8601=seconds)] kb-wiki-promote complete target=$TARGET_DATE"
  fi
} >> "$LOG_FILE" 2>&1
kb_finish_cron_run "kb-wiki-promote" "$TARGET_DATE" "$RUN_EXIT" "$LOG_FILE"
exit $?
