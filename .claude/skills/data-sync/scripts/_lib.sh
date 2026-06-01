# .claude/skills/data-sync/scripts/_lib.sh
# Shared helpers for the data-sync scripts. Source, do not execute.
# Resolves KB_ROOT from the *caller's* location is unreliable; each script
# computes KB_ROOT and exports DATA before sourcing.

# shellcheck disable=SC2034  # consumed by sync-data.sh / merge-data-pr.sh
LOCK_FILE_REL=".git/kb-sync.lock"   # under $DATA

# Parse owner/name out of a github URL (SSH or HTTPS).
parse_repo_slug() {
  local s="$1"
  s="${s#git@github.com:}"
  s="${s#ssh://git@github.com/}"
  s="${s#https://github.com/}"
  s="${s#http://github.com/}"
  s="${s%.git}"; s="${s%/}"
  printf '%s' "$s"
}

# The private repo is whatever data/'s own origin points at — set when the user
# clones (knowledgebase-initialize Phase 2) or attaches (setup-data-remote.sh)
# their private repo at init. Nothing is hardcoded. The guard still refuses a
# non-github origin so data/ can never be pushed to an unexpected host. On
# success it exports PRIVATE_REPO=owner/name. Call: assert_private_origin "$DATA"
PRIVATE_REPO="${PRIVATE_REPO:-}"
assert_private_origin() {
  local data="$1" url
  url="$(git -C "$data" remote get-url origin 2>/dev/null || true)"
  if [ -z "$url" ]; then
    echo "error: no 'origin' remote on $data. Clone your private repo into data/, or run setup-data-remote.sh." >&2
    return 1
  fi
  case "$url" in
    git@github.com:*|https://github.com/*|http://github.com/*) ;;
    *) echo "error: origin '$url' is not a github.com remote — refusing to push/PR data/ (privacy guard)." >&2
       return 1 ;;
  esac
  PRIVATE_REPO="$(parse_repo_slug "$url")"
  return 0
}

# Stable per-machine id, minted once and persisted to data/.sync-machine-id.
machine_id() {
  local data="$1" idfile="$1/.sync-machine-id" id slug rand
  if [ -f "$idfile" ]; then
    cat "$idfile"; return 0
  fi
  slug="$(hostname | tr '[:upper:]' '[:lower:]' | tr -c 'a-z0-9' '-' | sed 's/-\+/-/g; s/^-//; s/-$//')"
  [ -z "$slug" ] && slug="host"
  rand="$(_rand4)"
  id="${slug}-${rand}"
  printf '%s' "$id" > "$idfile" || { echo "error: cannot write $idfile" >&2; return 1; }
  printf '%s' "$id"
}

# 4 hex chars of randomness for branch-name disambiguation.
_rand4() {
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex 2
  else
    head -c2 /dev/urandom | od -An -tx1 | tr -d ' \n'
  fi
}

# Today's date in KST (matches the rest of the cron tooling).
kst_date() { TZ=Asia/Seoul date +%F; }

# Build a fresh work-branch name.
new_work_branch() { printf 'sync/%s-%s-%s' "$(machine_id "$1")" "$(kst_date)" "$(_rand4)"; }

# Ensure the per-machine id file is ignored locally (machine-local exclude, not
# the tracked .gitignore — it needs no commit and survives a master reset).
ensure_machine_id_ignored() {
  local data="$1" excl="$1/.git/info/exclude"
  [ -d "$1/.git/info" ] || return 0
  grep -qxF '.sync-machine-id' "$excl" 2>/dev/null || printf '%s\n' '.sync-machine-id' >> "$excl"
}

# KB_SYNC_TEST=1 disables the network allowlist guard for hermetic tests that
# push to a local bare remote. Refuse it against the live data/ tree so an
# inherited environment variable cannot disable production guards.
init_test_mode() {
  local data="$1" live_data="$2"
  TEST_MODE=0
  if [ "${KB_SYNC_TEST:-}" = "1" ]; then
    if [ -z "${KB_DATA_OVERRIDE:-}" ] || [ "$data" = "$live_data" ]; then
      echo "error: KB_SYNC_TEST=1 requires KB_DATA_OVERRIDE pointing at a non-live test repo." >&2
      return 1
    fi
    TEST_MODE=1
  fi
}

# KB_SYNC_LINT_CMD overrides the pre-flight lint command (tests only). The
# pre-flight lint is a MANDATORY gate — sync-data.sh refuses to push if it
# fails. Never set KB_SYNC_LINT_CMD outside the test suite.
