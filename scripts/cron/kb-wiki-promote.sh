#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KB_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
LOG_DIR="$KB_ROOT/.cron/logs"
LOCK_DIR="$KB_ROOT/.cron/locks"
TARGET_DATE="$(TZ=Asia/Seoul date -d 'yesterday' +%F)"

mkdir -p "$LOG_DIR" "$LOCK_DIR"

flock -n "$LOCK_DIR/wiki-promote.lock" bash -lc "
  cd '$KB_ROOT'
  opencode run \
    --model anthropic/claude-sonnet-4-6 \
    --dangerously-skip-permissions \
    --dir '$KB_ROOT' \
    'Run the KnowledgeBase wiki promotion workflow for $TARGET_DATE. Import and follow .claude/skills/wiki-approval/SKILL.md as the runtime contract. Import .claude/skills/wiki-authoring/SKILL.md only if page metadata/content fixes are needed before promotion. Do not read docs as runtime instructions. Promote worthy not_processed pages, leave borderline pages for TTL, write the wiki-promote handoff and data/log.md, and commit only the nested data repo if pages were promoted. Do not push.'
" >> "$LOG_DIR/wiki-promote.log" 2>&1
