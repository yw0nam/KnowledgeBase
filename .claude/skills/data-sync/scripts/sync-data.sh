#!/usr/bin/env bash
set -euo pipefail

# Publish the current work branch as a PR on the private remote, prune merged
# branches, and detect (not resolve) cross-machine conflicts.
# Usage: bash sync-data.sh [--dry-run]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KB_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
DATA="${KB_DATA_OVERRIDE:-$KB_ROOT/data}"
# shellcheck source=_lib.sh
source "$SCRIPT_DIR/_lib.sh"
init_test_mode "$DATA" "$KB_ROOT/data"

DRY_RUN="${1:-}"
[ -z "$DRY_RUN" ] || [ "$DRY_RUN" = "--dry-run" ] || { echo "error: only --dry-run supported" >&2; exit 2; }
[ -z "${KB_SYNC_LINT_CMD:-}" ] || [ "$TEST_MODE" = "1" ] \
  || { echo "error: KB_SYNC_LINT_CMD is test-only; refusing to bypass the production lint gate." >&2; exit 1; }
run() { echo "+ $*"; [ "$DRY_RUN" = "--dry-run" ] || "$@"; }

_print_conflict_help() {
  cat >&2 <<'EOF'
CONFLICT: origin/master moved and the work branch no longer applies cleanly.
Resolve manually in data/ (commit/stash in-session output first):
  git -C data rebase origin/master
    log.md      → keep both, sort by date
    wiki/**     → union the sources: arrays
    handoffs/** → keep the newer updated:
    raw/**      → conflict = immutability violation; investigate, do NOT blind-accept
  git -C data rebase --continue
  bash .claude/skills/data-sync/scripts/sync-data.sh   # re-run
EOF
}

# Mandatory pre-flight lint. Real run wires uv; tests override via KB_SYNC_LINT_CMD.
preflight_lint() {
  if [ -n "${KB_SYNC_LINT_CMD:-}" ]; then
    [ "$TEST_MODE" = "1" ] \
      || { echo "error: KB_SYNC_LINT_CMD is test-only; refusing to bypass the production lint gate." >&2; return 1; }
    eval "$KB_SYNC_LINT_CMD"; return $?
  fi
  ( cd "$KB_ROOT" \
    && KB_DATA_DIR="$DATA" uv run kb-wiki-index \
    && [ -z "$(git -C "$DATA" status --porcelain -- wiki/INDEX.md)" ] \
    && KB_DATA_DIR="$DATA" uv run kb-lint-wiki --check-immutability \
    && KB_DATA_DIR="$DATA" uv run kb-lint-handoff )
}

[ -d "$DATA/.git" ] || { echo "error: $DATA is not a git repo. Run knowledgebase-initialize / setup-data-workbranch.sh." >&2; exit 1; }

# Re-exec under flock on the canonical lock (shared with the cron wrapper) so
# no two syncs — or a sync and a cron commit — touch data/ at once. If flock is
# unavailable (e.g. macOS), degrade gracefully: all other guards still run.
LOCK="$DATA/$LOCK_FILE_REL"
if [ -z "${KB_SYNC_LOCKED:-}" ] && command -v flock >/dev/null 2>&1; then
  exec env KB_SYNC_LOCKED=1 flock -n "$LOCK" "$0" "$@"
fi

# ── Guards ───────────────────────────────────────────────────────────
WB="$(git -C "$DATA" symbolic-ref --short HEAD 2>/dev/null)" \
  || { echo "error: data/ is in detached HEAD (a prior sync may have crashed mid-reconcile). Resolve manually: git -C data checkout <branch>." >&2; exit 1; }
if [[ "$WB" != sync/* ]]; then
  echo "error: data/ is not on a work branch (HEAD=$WB). Run setup-data-workbranch.sh." >&2; exit 1
fi
[ "$TEST_MODE" = "1" ] || assert_private_origin "$DATA"
if [ "$TEST_MODE" != "1" ]; then
  gh auth status >/dev/null 2>&1 || { echo "error: gh not authenticated. Run: gh auth login" >&2; exit 1; }
fi
# Reconcile mints fresh work branches via new_work_branch → machine_id, which
# writes .sync-machine-id into data/. Ensure it's locally excluded up front so
# the conflict-abort path leaves a genuinely clean tree (not "?? .sync-machine-id").
ensure_machine_id_ignored "$DATA"

# ── Fetch ────────────────────────────────────────────────────────────
run git -C "$DATA" fetch origin
[ "$DRY_RUN" = "--dry-run" ] && echo "  (dry-run: origin not fetched; ahead-counts and PR-state below may be stale)"

# ── Post-merge reconcile (commit-loss-safe) ─────────────────────────
pr_state() {
  if [ "$TEST_MODE" = "1" ]; then
    printf '%s %s\n' "${KB_SYNC_FAKE_PR_STATE:-OPEN}" "${KB_SYNC_FAKE_PR_MERGEABLE:-MERGEABLE}"
    return
  fi
  gh pr view "$WB" --repo "$PRIVATE_REPO" --json state,mergeable \
    -q '.state + " " + .mergeable' 2>/dev/null || echo "NONE UNKNOWN"
}

if [ "$DRY_RUN" = "--dry-run" ]; then
  echo "+ (dry-run) post-merge reconcile skipped (would inspect PR state, prune a merged branch, or cherry-pick leftover commits)"
else
  read -r STATE MERGEABLE <<< "$(pr_state)"
  LEFTOVER="$(git -C "$DATA" rev-list --count origin/master.."$WB" 2>/dev/null || echo 0)"

  if [ "$STATE" = "MERGED" ]; then
    # Cheap assert: with repo-level merge-commit enforcement the branch tip is an
    # ancestor of origin/master once leftover is empty (spec §4.3, C3).
    if [ "$LEFTOVER" = "0" ]; then
      NEW="$(new_work_branch "$DATA")"
      run git -C "$DATA" checkout -b "$NEW" origin/master
      run git -C "$DATA" branch -D "$WB"
      run git -C "$DATA" push origin --delete "$WB" || true
      WB="$NEW"
    else
      # Leftover = genuinely new commits after the synced push. Cherry-pick onto
      # a fresh branch off origin/master; on conflict, abort + hand to the user.
      NEW="$(new_work_branch "$DATA")"
      run git -C "$DATA" checkout -b "$NEW" origin/master
      if ! git -C "$DATA" cherry-pick "origin/master..$WB" 2>/dev/null; then
        git -C "$DATA" cherry-pick --abort 2>/dev/null || true
        git -C "$DATA" checkout "$WB"
        git -C "$DATA" branch -D "$NEW" 2>/dev/null || true
        _print_conflict_help; exit 1
      fi
      run git -C "$DATA" branch -D "$WB"
      run git -C "$DATA" push origin --delete "$WB" || true
      WB="$NEW"
    fi
  elif [ "$STATE" = "CLOSED" ]; then
    echo "error: PR for $WB is CLOSED (not merged). Reopen it, or cut a fresh branch" >&2
    echo "       discarding the work, then re-run. Refusing to auto-recreate the PR." >&2
    exit 1
  elif [ "$STATE" = "OPEN" ] && [ "$MERGEABLE" = "CONFLICTING" ]; then
    _print_conflict_help
    exit 1
  fi
fi

# ── Nothing-to-sync ──────────────────────────────────────────────────
# Work branch not ahead of origin/master and no open PR.
AHEAD="$(git -C "$DATA" rev-list --count origin/master.."$WB" 2>/dev/null || echo 0)"
if [ "$AHEAD" = "0" ]; then
  echo "nothing to sync (work branch not ahead of origin/master)."; exit 0
fi

# Dirty-tree warning (spec §4.3 step 4): only committed work syncs. Warn, do not auto-commit.
[ -z "$(git -C "$DATA" status --porcelain)" ] \
  || echo "warning: data/ has uncommitted changes — only committed work will appear in the PR." >&2

# ── Pre-flight lint — MANDATORY blocking gate (spec §4.3 step 6) ─────────
# Bad data never leaves the machine: if lint fails, abort BEFORE push/PR.
if [ "$DRY_RUN" = "--dry-run" ]; then
  echo "+ preflight lint (would run; skipped in --dry-run)"
else
  preflight_lint || { echo "error: pre-flight lint failed — refusing to push." >&2; exit 1; }
fi

# ── Push (only reached if lint passed) ──────────────────────────────────
run git -C "$DATA" push -u origin "$WB"

# ── PR (create or update) ──────────────────────────────────────────────
if [ "$TEST_MODE" = "1" ]; then
  echo "+ gh pr create --repo $PRIVATE_REPO --base master --head $WB  (skipped in test)"
  exit 0
fi
EXISTING_PR="$(gh pr list --repo "$PRIVATE_REPO" --head "$WB" --json url -q '.[0].url' 2>/dev/null || true)"
if [ -n "$EXISTING_PR" ]; then
  echo "PR already open (push updated it): $EXISTING_PR"
else
  BODY="$(git -C "$DATA" log origin/master.."$WB" --oneline)"
  run gh pr create --repo "$PRIVATE_REPO" --base master --head "$WB" \
    --title "data sync: $WB" --body "$BODY"
fi
