# .claude/skills/data-sync/scripts/_lib.sh
# Shared helpers for the data-sync scripts. Source, do not execute.
# Resolves KB_ROOT from the *caller's* location is unreliable; each script
# computes KB_ROOT and exports DATA before sourcing.

PRIVATE_REPO="yw0nam/PrivateKnowledgeBase"
# shellcheck disable=SC2034  # consumed by sync-data.sh
LOCK_FILE_REL=".git/kb-sync.lock"   # under $DATA

# Allowlist guard: refuse unless data/ origin matches the private repo in
# either SSH or HTTPS form. Allowlist (not denylist) so a new public host
# cannot slip through. Call: assert_private_origin "$DATA"
assert_private_origin() {
  local data="$1" url
  url="$(git -C "$data" remote get-url origin 2>/dev/null || true)"
  if [ -z "$url" ]; then
    echo "error: no 'origin' remote on $data. Run setup-data-remote.sh first." >&2
    return 1
  fi
  case "$url" in
    "git@github.com:$PRIVATE_REPO".git|"git@github.com:$PRIVATE_REPO") return 0 ;;
    "https://github.com/$PRIVATE_REPO".git|"https://github.com/$PRIVATE_REPO") return 0 ;;
  esac
  echo "error: origin '$url' is not the allowed private remote ($PRIVATE_REPO)." >&2
  echo "       refusing to push/PR data/ to a non-allowlisted host (privacy guard)." >&2
  return 1
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
# push to a local bare remote. Never set this outside the test suite.
