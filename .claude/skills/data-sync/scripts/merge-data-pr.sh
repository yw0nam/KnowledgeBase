#!/usr/bin/env bash
set -euo pipefail

# Free-plan merge gate for the current data/ work branch. GitHub Free private
# repos cannot enforce protected branches, so this is the supported merge path.
# Usage: bash merge-data-pr.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KB_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
DATA="${KB_DATA_OVERRIDE:-$KB_ROOT/data}"
# shellcheck source=_lib.sh
source "$SCRIPT_DIR/_lib.sh"
init_test_mode "$DATA" "$KB_ROOT/data"

[ "$#" -eq 0 ] || { echo "usage: bash merge-data-pr.sh" >&2; exit 2; }
[ -d "$DATA/.git" ] || { echo "error: $DATA is not a git repo." >&2; exit 1; }

LOCK="$DATA/$LOCK_FILE_REL"
if [ -z "${KB_SYNC_LOCKED:-}" ] && command -v flock >/dev/null 2>&1; then
  exec env KB_SYNC_LOCKED=1 flock -n "$LOCK" "$0" "$@"
fi

WB="$(git -C "$DATA" symbolic-ref --short HEAD 2>/dev/null)" \
  || { echo "error: data/ is in detached HEAD. Check out its sync/ work branch first." >&2; exit 1; }
[[ "$WB" == sync/* ]] \
  || { echo "error: data/ is not on a sync/ work branch (HEAD=$WB)." >&2; exit 1; }
[ "$TEST_MODE" = "1" ] || assert_private_origin "$DATA"

if [ "$TEST_MODE" = "1" ]; then
  STATE="${KB_SYNC_FAKE_PR_STATE:-OPEN}"
  MERGEABLE="${KB_SYNC_FAKE_PR_MERGEABLE:-MERGEABLE}"
  HEAD_SHA="${KB_SYNC_FAKE_HEAD_SHA:-test-head-sha}"
  LINT_BUCKET="${KB_SYNC_FAKE_LINT_BUCKET:-pass}"
else
  gh auth status >/dev/null 2>&1 \
    || { echo "error: gh not authenticated. Run: gh auth login" >&2; exit 1; }
  read -r STATE MERGEABLE HEAD_SHA <<< "$(
    gh pr view "$WB" --repo "$PRIVATE_REPO" --json state,mergeable,headRefOid \
      -q '.state + " " + .mergeable + " " + .headRefOid'
  )"
  gh pr checks "$WB" --repo "$PRIVATE_REPO" --watch --fail-fast
  LINT_BUCKET="$(
    gh pr checks "$WB" --repo "$PRIVATE_REPO" --json name,bucket \
      -q '.[] | select(.name == "lint") | .bucket'
  )"
fi

[ "$STATE" = "OPEN" ] \
  || { echo "error: PR for $WB is not OPEN (state=$STATE)." >&2; exit 1; }
[ "$MERGEABLE" = "MERGEABLE" ] \
  || { echo "error: PR for $WB is not mergeable (mergeable=$MERGEABLE). Resolve conflicts first." >&2; exit 1; }
[ "$LINT_BUCKET" = "pass" ] \
  || { echo "error: remote lint check did not pass (bucket=${LINT_BUCKET:-missing}). Refusing to merge." >&2; exit 1; }

if [ "$TEST_MODE" = "1" ]; then
  echo "+ gh pr merge $WB --repo $PRIVATE_REPO --merge --match-head-commit $HEAD_SHA"
  exit 0
fi

gh pr merge "$WB" --repo "$PRIVATE_REPO" --merge --match-head-commit "$HEAD_SHA"
echo "ok: merged $WB after remote lint passed. Re-run sync-data.sh to reconcile onto a fresh work branch."
