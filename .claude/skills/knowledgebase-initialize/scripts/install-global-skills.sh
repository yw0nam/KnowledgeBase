#!/usr/bin/env bash
set -euo pipefail

# Symlink the repo skills that are meant to be used OUTSIDE this repo into the
# user's global Claude skills dir (~/.claude/skills). The repo is the source of
# truth; symlinks never drift (a manual copy does — that is the bug this fixes).
# Idempotent. Usage: bash install-global-skills.sh [--dry-run]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# skill is at .claude/skills/knowledgebase-initialize/scripts → KB_ROOT is 4 levels up
KB_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
DEST_DIR="${CLAUDE_SKILLS_DIR:-$HOME/.claude/skills}"
# Backups go OUTSIDE the scanned skills dir, or they get loaded as duplicate skills.
BACKUP_DIR="${CLAUDE_SKILLS_BACKUP_DIR:-${DEST_DIR%/}.pre-symlink-backups}"

# Skills exposed globally. Add a bare skill-dir name to expose more.
GLOBAL_SKILLS=(handoff-document wiki-note)

DRY_RUN="${1:-}"
[ -z "$DRY_RUN" ] || [ "$DRY_RUN" = "--dry-run" ] || { echo "error: only --dry-run supported" >&2; exit 2; }
run() { echo "+ $*"; [ "$DRY_RUN" = "--dry-run" ] || "$@"; }

run mkdir -p "$DEST_DIR"

for name in "${GLOBAL_SKILLS[@]}"; do
  src="$KB_ROOT/.claude/skills/$name"
  dst="$DEST_DIR/$name"
  [ -d "$src" ] || { echo "error: repo skill not found: $src" >&2; exit 1; }

  # Already the correct symlink → no-op.
  if [ -L "$dst" ] && [ "$(readlink "$dst")" = "$src" ]; then
    echo "ok: $name already symlinked → $src"
    continue
  fi

  # A real dir/file here is a (possibly drifted) manual copy. Back it up, never
  # delete — the user may have local edits worth keeping.
  if [ -e "$dst" ] && [ ! -L "$dst" ]; then
    bak="$BACKUP_DIR/$name"
    [ ! -e "$bak" ] || { echo "error: backup target exists: $bak (remove it, then re-run)." >&2; exit 1; }
    echo "note: $dst is a real copy (may have drifted) — backing up to $bak"
    run mkdir -p "$BACKUP_DIR"
    run mv "$dst" "$bak"
  elif [ -L "$dst" ]; then
    # Stale symlink pointing elsewhere → replace.
    run rm "$dst"
  fi

  run ln -s "$src" "$dst"
  echo "ok: $name → $src"
done
