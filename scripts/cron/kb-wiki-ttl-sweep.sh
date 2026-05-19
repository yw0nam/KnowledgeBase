#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KB_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
LOG_DIR="$KB_ROOT/.cron/logs"
LOCK_DIR="$KB_ROOT/.cron/locks"

mkdir -p "$LOG_DIR" "$LOCK_DIR"

if ! flock -n "$LOCK_DIR/wiki-ttl-sweep.lock" \
    bash -lc "cd '$KB_ROOT' && uv run kb-wiki-review ttl-sweep --days 7" \
    >> "$LOG_DIR/wiki-ttl-sweep.log" 2>&1; then
  echo "[$(date -Iseconds)] ERROR: kb-wiki-ttl-sweep failed" >&2
  exit 1
fi
