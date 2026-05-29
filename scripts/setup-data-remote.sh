#!/usr/bin/env bash
set -euo pipefail

# Configure a private git remote for the nested data/ repo so it can sync
# across machines. See docs/data-sync.md for the full workflow.
#
# Usage:
#   bash scripts/setup-data-remote.sh <git-url>
#   bash scripts/setup-data-remote.sh <git-url> --dry-run

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KB_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DATA="$KB_ROOT/data"

URL="${1:-}"
DRY_RUN="${2:-}"

if [ -z "$URL" ] || [[ "$URL" == --* ]]; then
  echo "usage: bash scripts/setup-data-remote.sh <git-url> [--dry-run]" >&2
  exit 2
fi
if [ -n "$DRY_RUN" ] && [ "$DRY_RUN" != "--dry-run" ]; then
  echo "error: unknown flag '$DRY_RUN' (only --dry-run supported)" >&2
  exit 2
fi

if [ ! -d "$DATA" ]; then
  echo "error: $DATA does not exist. Run knowledgebase-initialize first." >&2
  exit 1
fi
if [ ! -d "$DATA/.git" ]; then
  echo "error: $DATA is not a git repo." >&2
  exit 1
fi

if ! git -C "$DATA" diff --quiet || ! git -C "$DATA" diff --cached --quiet; then
  echo "error: $DATA has uncommitted changes. Commit or stash first." >&2
  exit 1
fi

EXISTING="$(git -C "$DATA" remote get-url origin 2>/dev/null || true)"
if [ -n "$EXISTING" ]; then
  if [ "$EXISTING" = "$URL" ]; then
    echo "ok: origin already set to $URL (no-op)"
    exit 0
  fi
  echo "error: origin already set to a different url: $EXISTING" >&2
  echo "       to change, run: git -C $DATA remote set-url origin <url>" >&2
  exit 1
fi

BRANCH="$(git -C "$DATA" symbolic-ref --short HEAD)"

run() {
  echo "+ $*"
  if [ "$DRY_RUN" != "--dry-run" ]; then
    "$@"
  fi
}

run git -C "$DATA" remote add origin "$URL"
run git -C "$DATA" push -u origin "$BRANCH"

if [ "$DRY_RUN" != "--dry-run" ]; then
  echo
  echo "remote configured:"
  git -C "$DATA" remote -v
fi
