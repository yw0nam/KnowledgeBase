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

# Privacy allowlist: the URL we are about to attach must be the private repo.
case "$URL" in
  "git@github.com:$PRIVATE_REPO".git|"git@github.com:$PRIVATE_REPO") ;;
  "https://github.com/$PRIVATE_REPO".git|"https://github.com/$PRIVATE_REPO") ;;
  *) echo "error: '$URL' is not the allowed private remote ($PRIVATE_REPO)." >&2; exit 1 ;;
esac

[ -d "$DATA" ] || { echo "error: $DATA does not exist. Run knowledgebase-initialize first." >&2; exit 1; }
[ -d "$DATA/.git" ] || { echo "error: $DATA is not a git repo." >&2; exit 1; }

if ! git -C "$DATA" diff --quiet || ! git -C "$DATA" diff --cached --quiet; then
  echo "error: $DATA has uncommitted changes. Commit or stash first." >&2; exit 1
fi

EXISTING="$(git -C "$DATA" remote get-url origin 2>/dev/null || true)"
if [ -n "$EXISTING" ] && [ "$EXISTING" != "$URL" ]; then
  echo "error: origin already set to a different url: $EXISTING" >&2; exit 1
fi

BRANCH="$(git -C "$DATA" symbolic-ref --short HEAD)"
run() { echo "+ $*"; [ "$DRY_RUN" = "--dry-run" ] || "$@"; }

[ -z "$EXISTING" ] && run git -C "$DATA" remote add origin "$URL"
run git -C "$DATA" push -u origin "$BRANCH"

# Enforce merge-commit at the repo level so squash/rebase merges are
# impossible (the sync pruning logic depends on merge-commit — spec §4.2).
run gh api -X PATCH "repos/$PRIVATE_REPO" \
  -F allow_merge_commit=true -F allow_squash_merge=false -F allow_rebase_merge=false

[ "$DRY_RUN" = "--dry-run" ] || { echo; echo "remote configured:"; git -C "$DATA" remote -v; }
