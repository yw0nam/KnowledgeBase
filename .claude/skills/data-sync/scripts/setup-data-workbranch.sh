#!/usr/bin/env bash
set -euo pipefail

# One-time: move data/ from master onto a work branch cut from origin/master.
# Carries any commits master was ahead by; resets local master to origin/master.
# Usage: bash setup-data-workbranch.sh [--dry-run]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KB_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
DATA="${KB_DATA_OVERRIDE:-$KB_ROOT/data}"
# shellcheck source=_lib.sh
source "$SCRIPT_DIR/_lib.sh"

DRY_RUN="${1:-}"
[ -z "$DRY_RUN" ] || [ "$DRY_RUN" = "--dry-run" ] || { echo "error: only --dry-run supported" >&2; exit 2; }
[ -d "$DATA/.git" ] || { echo "error: $DATA is not a git repo." >&2; exit 1; }

HEAD_BRANCH="$(git -C "$DATA" symbolic-ref --short HEAD)"
if [[ "$HEAD_BRANCH" == sync/* ]]; then
  echo "ok: data/ already on a work branch ($HEAD_BRANCH) — no-op"; exit 0
fi
if [ "$HEAD_BRANCH" != "master" ]; then
  echo "error: expected HEAD on master or a sync/ branch, found '$HEAD_BRANCH'." >&2; exit 1
fi

# 1. Refuse dirty tree (checkout -b would silently carry untracked/modified files).
if ! git -C "$DATA" diff --quiet || ! git -C "$DATA" diff --cached --quiet \
   || [ -n "$(git -C "$DATA" status --porcelain)" ]; then
  echo "error: $DATA has uncommitted changes. Commit or stash first." >&2; exit 1
fi

[ "${KB_SYNC_TEST:-}" = "1" ] || assert_private_origin "$DATA"

# Ensure the machine-local id file is git-ignored before it is minted, so it
# never shows as untracked or gets committed (it is per-machine, not shared).
ensure_machine_id_ignored "$DATA"

WB="$(new_work_branch "$DATA")"
run() { echo "+ $*"; [ "$DRY_RUN" = "--dry-run" ] || "$@"; }

# 2. fetch  3. cut work branch from current master HEAD (carries ahead commits)
run git -C "$DATA" fetch origin
run git -C "$DATA" checkout -b "$WB"
# 4. assert HEAD != master, then reset local master to origin/master
[ "$(git -C "$DATA" symbolic-ref --short HEAD)" != "master" ] || { echo "error: still on master" >&2; exit 1; }
run git -C "$DATA" branch -f master origin/master

echo "ok: data/ now on $WB; local master mirrors origin/master."
