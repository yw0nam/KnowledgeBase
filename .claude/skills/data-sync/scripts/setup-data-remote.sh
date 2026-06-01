#!/usr/bin/env bash
set -euo pipefail

# Attach a private origin to data/, enforce merge-commit at the repo level,
# and do the initial push. Setup action — run by the user, never by cron.
# Usage: bash setup-data-remote.sh <git-url> [--dry-run]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# skill is at .claude/skills/data-sync/scripts → KB_ROOT is 4 levels up
KB_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
DATA="${KB_DATA_OVERRIDE:-$KB_ROOT/data}"
# shellcheck source=_lib.sh
source "$SCRIPT_DIR/_lib.sh"

URL="${1:-}"; DRY_RUN="${2:-}"
if [ -z "$URL" ] || [[ "$URL" == --* ]]; then
  echo "usage: bash setup-data-remote.sh <git-url> [--dry-run]" >&2; exit 2
fi
if [ -n "$DRY_RUN" ] && [ "$DRY_RUN" != "--dry-run" ]; then
  echo "error: unknown flag '$DRY_RUN' (only --dry-run supported)" >&2; exit 2
fi

# The user supplies the private repo here. Require a github.com SSH/HTTPS URL
# and derive owner/name from it (nothing is hardcoded). Never point this at the
# outer repo's URL or any public host — that stays the operator's responsibility.
case "$URL" in
  git@github.com:*|https://github.com/*|http://github.com/*) ;;
  *) echo "error: '$URL' is not a github.com SSH or HTTPS git URL." >&2; exit 1 ;;
esac
PRIVATE_REPO="$(parse_repo_slug "$URL")"
case "$PRIVATE_REPO" in
  */*) ;;
  *) echo "error: '$URL' did not parse to an owner/name repo." >&2; exit 1 ;;
esac

[ -d "$DATA" ] || { echo "error: $DATA does not exist. Run knowledgebase-initialize first." >&2; exit 1; }
[ -d "$DATA/.git" ] || { echo "error: $DATA is not a git repo." >&2; exit 1; }

if ! git -C "$DATA" diff --quiet || ! git -C "$DATA" diff --cached --quiet \
   || [ -n "$(git -C "$DATA" status --porcelain)" ]; then
  echo "error: $DATA has uncommitted changes. Commit or stash first." >&2; exit 1
fi

run() { echo "+ $*"; [ "$DRY_RUN" = "--dry-run" ] || "$@"; }

EXISTING="$(git -C "$DATA" remote get-url origin 2>/dev/null || true)"
if [ -n "$EXISTING" ] && [ "$EXISTING" != "$URL" ]; then
  echo "error: origin already set to a different url: $EXISTING" >&2
  echo "       to change, run: git -C $DATA remote set-url origin <url>" >&2
  exit 1
fi
if [ -n "$EXISTING" ] && [ "$EXISTING" = "$URL" ]; then
  echo "ok: origin already set to $URL"
  run gh api -X PATCH "repos/$PRIVATE_REPO" \
    -F allow_merge_commit=true -F allow_squash_merge=false -F allow_rebase_merge=false
  echo "ok: merge-commit policy enforced"
  exit 0
fi

BRANCH="$(git -C "$DATA" symbolic-ref --short HEAD)"

[ -z "$EXISTING" ] && run git -C "$DATA" remote add origin "$URL"
run git -C "$DATA" push -u origin "$BRANCH"

# Enforce merge-commit at the repo level so squash/rebase merges are
# impossible (the sync pruning logic depends on merge-commit — spec §4.2).
run gh api -X PATCH "repos/$PRIVATE_REPO" \
  -F allow_merge_commit=true -F allow_squash_merge=false -F allow_rebase_merge=false

[ "$DRY_RUN" = "--dry-run" ] || { echo; echo "remote configured:"; git -C "$DATA" remote -v; }
