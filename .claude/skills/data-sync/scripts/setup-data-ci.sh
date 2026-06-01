#!/usr/bin/env bash
set -euo pipefail

# Install the CI lint workflow onto origin/master. Must run while data/ is on
# master (C4 — no throwaway worktree). Usage: bash setup-data-ci.sh <pin> [--dry-run]
#   <pin> = a tag or SHA of yw0nam/KnowledgeBase that includes the KB_DATA_DIR change.
# Note: --dry-run skips fetch/merge, so its no-op check compares against the local lint.yml, not origin/master.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KB_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
DATA="${KB_DATA_OVERRIDE:-$KB_ROOT/data}"
# shellcheck source=_lib.sh
source "$SCRIPT_DIR/_lib.sh"
init_test_mode "$DATA" "$KB_ROOT/data"

PIN="${1:-}"; DRY_RUN="${2:-}"
[ -n "$PIN" ] && [[ "$PIN" != --* ]] || { echo "usage: bash setup-data-ci.sh <tag-or-sha> [--dry-run]" >&2; exit 2; }
[ -z "$DRY_RUN" ] || [ "$DRY_RUN" = "--dry-run" ] || { echo "error: only --dry-run supported" >&2; exit 2; }
[ -d "$DATA/.git" ] || { echo "error: $DATA is not a git repo." >&2; exit 1; }

# C4: refuse on a work branch.
HEAD_BRANCH="$(git -C "$DATA" symbolic-ref --short HEAD)"
if [ "$HEAD_BRANCH" != "master" ]; then
  echo "error: CI bootstrap must run on 'master' (found '$HEAD_BRANCH')." >&2
  echo "       Run setup-data-ci.sh during init before setup-data-workbranch.sh," >&2
  echo "       or temporarily: git -C $DATA checkout master" >&2
  exit 1
fi

[ "$TEST_MODE" = "1" ] || assert_private_origin "$DATA"

run() { echo "+ $*"; [ "$DRY_RUN" = "--dry-run" ] || "$@"; }

# Base the commit on current origin/master (avoid non-ff from a stale master).
run git -C "$DATA" fetch origin
run git -C "$DATA" merge --ff-only origin/master

DEST="$DATA/.github/workflows"
TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT
sed "s|__KB_PIN__|$PIN|g" "$SCRIPT_DIR/../reference/data-lint.yml" > "$TMP"

if [ -f "$DEST/lint.yml" ] && cmp -s "$TMP" "$DEST/lint.yml"; then
  echo "ok: lint.yml unchanged — no-op"
  exit 0
fi
[ "$DRY_RUN" = "--dry-run" ] && { echo "+ install lint.yml (pin=$PIN)"; exit 0; }
mkdir -p "$DEST"
cp "$TMP" "$DEST/lint.yml"

run git -C "$DATA" add .github/workflows/lint.yml
run git -C "$DATA" commit -m "ci: add data lint workflow"
run git -C "$DATA" push origin master   # NO force; on non-ff the user re-fetches and retries
echo "ok: CI lint workflow installed (pin=$PIN)."
