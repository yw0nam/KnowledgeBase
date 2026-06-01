# PR-Based `data/` Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace direct `git push origin master` of the nested `data/` repo with a work-branch → PR → merge-commit model on the private remote, with remote CI lint, a self-contained `data-sync` skill, and privacy guardrails.

**Architecture:** `data/` always rides a work branch `sync/<machine>-<date>-<rand>` cut from `origin/master`; local `master` is never hand-committed. AI/cron sessions commit to the work branch; a shell helper (`sync-data.sh`, outside any AI session) pushes + opens a PR; after review the user runs `merge-data-pr.sh`, which verifies remote lint and pins the head SHA before merge-commit; the next sync prunes the merged branch and cuts a fresh one. Cross-machine conflicts are detected and handed to the user, not auto-resolved (simplicity decisions C1–C4 in the spec §12).

**Tech Stack:** Python 3.11 (`uv`, pytest), Bash (`gh`, `git`, `flock`), GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-05-29-pr-based-data-sync-design.md` — read §4 (architecture), §9 (error handling), §12 (review log) before starting.

**Commit sequencing (one outer-repo PR):** Phase 1 (`KB_DATA_DIR`) commits FIRST and is the commit the CI pin will reference (spec §4.4/§7). Phases 2–4 follow. Land the whole PR to `main`, then wire the CI pin to the merge SHA (Task 17).

**Conventions to match (verified in the repo):**
- Shell scripts: `#!/usr/bin/env bash` + `set -euo pipefail`; resolve `KB_ROOT` from `$SCRIPT_DIR`; support `--dry-run` via a `run()` wrapper that echoes `+ cmd` (see `scripts/setup-data-remote.sh`).
- Shell scripts are tested from **pytest via `subprocess`** (no `bats` in this repo — see `test/test_lint_wiki.py` which already shells out). Assert on exit code and stdout/stderr.
- Private remote: `yw0nam/PrivateKnowledgeBase`. Outer (public): `yw0nam/KnowledgeBase`.
- Run Python tests with `uv run pytest`. Run `./scripts/lint.sh` before committing Python.

---

## File Structure

**Created:**
- `src/kb/__init__.py` — add `data_dir()` helper (modify; see Task 1).
- `.claude/skills/data-sync/SKILL.md` — runtime contract.
- `.claude/skills/data-sync/scripts/setup-data-remote.sh` — moved from `scripts/`, + merge-method API flags + allowlist guard.
- `.claude/skills/data-sync/scripts/setup-data-workbranch.sh` — onboarding/migration onto a work branch.
- `.claude/skills/data-sync/scripts/setup-data-ci.sh` — CI workflow installer into `data/`.
- `.claude/skills/data-sync/scripts/sync-data.sh` — the sync helper.
- `.claude/skills/data-sync/scripts/merge-data-pr.sh` — GitHub Free private-repo merge gate.
- `.claude/skills/data-sync/scripts/_lib.sh` — shared bash helpers (allowlist guard, machine-id, lock path).
- `.claude/skills/data-sync/reference/data-lint.yml` — CI workflow template (with a `__KB_PIN__` placeholder).
- `docs/data-sync.md` — rewrite (was created in a prior PR).
- `test/test_data_dir.py` — `data_dir()` unit tests.
- `test/test_cli_data_dir.py` — subprocess tests that the 3 CLIs honor `KB_DATA_DIR`.
- `test/test_data_sync_scripts.py` — subprocess tests for the bash scripts (guards, dry-run, idempotency).

**Modified:**
- `src/kb/cli/lint_wiki.py`, `src/kb/cli/wiki_index.py`, `src/kb/cli/lint_handoff.py` — `main()` resolves data dir from `KB_DATA_DIR`.
- `scripts/cron/kb-cron-wrapup.sh` — extend `flock` scope; call `sync-data.sh`.
- `.claude/skills/knowledgebase-initialize/SKILL.md`, `.claude/skills/cron-wrapup/SKILL.md`, `.claude/skills/wiki-approval/SKILL.md` — text touch-ups + init phases.
- `CHANGELOG.md` — outer-repo entry.

**Deleted:**
- `scripts/setup-data-remote.sh` (moved into the skill — Task 6).

---

## Phase 1 — `KB_DATA_DIR` CLI prerequisite (commits first; CI pin references this)

### Task 1: Add `kb.data_dir()` helper

**Files:**
- Modify: `src/kb/__init__.py`
- Test: `test/test_data_dir.py`

- [ ] **Step 1: Write the failing test**

```python
# test/test_data_dir.py
"""Tests for kb.data_dir() — KB_DATA_DIR resolution."""

from __future__ import annotations

from pathlib import Path

import kb


def test_data_dir_defaults_to_repo_root_data(monkeypatch):
    monkeypatch.delenv("KB_DATA_DIR", raising=False)
    assert kb.data_dir() == (kb.REPO_ROOT / "data").resolve()


def test_data_dir_honors_env(monkeypatch, tmp_path):
    monkeypatch.setenv("KB_DATA_DIR", str(tmp_path))
    assert kb.data_dir() == tmp_path.resolve()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest test/test_data_dir.py -v`
Expected: FAIL with `AttributeError: module 'kb' has no attribute 'data_dir'`

- [ ] **Step 3: Add the helper**

```python
# src/kb/__init__.py
"""kb — KnowledgeBase lint and reporting CLI tooling."""

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def data_dir() -> Path:
    """Resolve the data tree root from ``KB_DATA_DIR`` (default ``<repo>/data``).

    Matches ``src/kb/web/config.py`` semantics: the variable is the data
    *root*; ``wiki/``, ``raw/``, ``handoffs/`` are derived as children.
    """
    return Path(os.environ.get("KB_DATA_DIR", str(REPO_ROOT / "data"))).resolve()


__all__ = ["REPO_ROOT", "data_dir"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest test/test_data_dir.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/kb/__init__.py test/test_data_dir.py
git commit -m "feat(cli): add kb.data_dir() KB_DATA_DIR resolver"
```

### Task 2: Wire `kb-lint-wiki` to `KB_DATA_DIR`

**Files:**
- Modify: `src/kb/cli/lint_wiki.py:377-395` (the `main()` function)
- Test: `test/test_cli_data_dir.py`

- [ ] **Step 1: Write the failing test**

```python
# test/test_cli_data_dir.py
"""Subprocess tests: the CLIs target KB_DATA_DIR, not the repo default."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def _run(module: str, data_dir: Path) -> subprocess.CompletedProcess:
    env = dict(os.environ, KB_DATA_DIR=str(data_dir))
    return subprocess.run(
        [sys.executable, "-m", module],
        capture_output=True,
        text=True,
        env=env,
    )


def _make_wiki(root: Path) -> None:
    for sub in ("entities", "concepts", "decisions", "questions",
                "improvements", "checklists", "summaries"):
        (root / "wiki" / sub).mkdir(parents=True, exist_ok=True)
    (root / "raw").mkdir(parents=True, exist_ok=True)


def test_lint_wiki_lints_kb_data_dir(tmp_path):
    _make_wiki(tmp_path)
    # A page with a dead wikilink → a deterministic ERROR proving the lint
    # read THIS tree (not the repo's real data/).
    page = tmp_path / "wiki" / "concepts" / "Bad.md"
    page.write_text(
        '---\ntype: concept\nreview_status: approved\n'
        'created: "2026-05-01"\nupdated: "2026-05-01"\nsources: []\ntags: []\n---\n\n'
        "Body links to [[NonexistentTarget]].\n"
    )
    proc = _run("kb.cli.lint_wiki", tmp_path)
    assert proc.returncode == 1
    assert "dead link [[NonexistentTarget]]" in proc.stdout
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest test/test_cli_data_dir.py::test_lint_wiki_lints_kb_data_dir -v`
Expected: FAIL — the lint reads `<repo>/data/wiki` (the default), so the dead link in `tmp_path` is never seen (returncode 0 or unrelated output).

- [ ] **Step 3: Wire `main()` to the resolver**

```python
# src/kb/cli/lint_wiki.py — replace main()
def main():
    from kb import data_dir

    strict = "--strict" in sys.argv
    check_immutability = "--check-immutability" in sys.argv or strict

    dd = data_dir()
    print(f"Linting {dd / 'wiki'}/...\n")

    result = LintResult()
    lint(
        result,
        wiki_dir=dd / "wiki",
        raw_dir=dd / "raw",
        check_immutability=check_immutability,
    )
    result.print_report()

    if not result.ok:
        print("\nFAILED — fix errors before committing.")
        sys.exit(1)
    elif strict and result.warnings:
        print("\nFAILED (--strict) — warnings treated as errors.")
        sys.exit(1)
    else:
        print("\nPASSED")
        sys.exit(0)
```

(The module-level `WIKI_DIR`/`RAW_DIR` and `lint()`'s `None` defaults stay unchanged — surgical; only `main()` now passes explicit dirs.)

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest test/test_cli_data_dir.py::test_lint_wiki_lints_kb_data_dir -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/kb/cli/lint_wiki.py test/test_cli_data_dir.py
git commit -m "feat(cli): kb-lint-wiki honors KB_DATA_DIR"
```

### Task 3: Wire `kb-wiki-index` to `KB_DATA_DIR`

**Files:**
- Modify: `src/kb/cli/wiki_index.py:18-29` (the `main()` function)
- Test: `test/test_cli_data_dir.py` (append)

- [ ] **Step 1: Write the failing test (append to test_cli_data_dir.py)**

```python
def test_wiki_index_writes_into_kb_data_dir(tmp_path):
    _make_wiki(tmp_path)
    proc = _run("kb.cli.wiki_index", tmp_path)
    assert proc.returncode == 0
    assert (tmp_path / "wiki" / "INDEX.md").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest test/test_cli_data_dir.py::test_wiki_index_writes_into_kb_data_dir -v`
Expected: FAIL — `INDEX.md` is written under `<repo>/data/wiki`, not `tmp_path`, so the assertion that `tmp_path/wiki/INDEX.md` exists fails (and the run may even error if `<repo>/data/wiki` is absent in a worktree).

- [ ] **Step 3: Wire `main()` to the resolver**

```python
# src/kb/cli/wiki_index.py — replace main()
def main() -> None:
    from kb import data_dir

    wiki_dir = data_dir() / "wiki"
    if not wiki_dir.exists():
        print(f"ERROR: {wiki_dir} does not exist", file=sys.stderr)
        sys.exit(1)

    content = build_index(wiki_dir)
    out_path = wiki_dir / INDEX_FILENAME
    if out_path.exists() and out_path.read_text() == content:
        print(f"INDEX.md already in sync ({out_path})")
        return
    out_path.write_text(content)
    print(f"Wrote {out_path}")
```

(Leave the module-level `WIKI_DIR` for any importers; `main()` no longer uses it.)

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest test/test_cli_data_dir.py::test_wiki_index_writes_into_kb_data_dir -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/kb/cli/wiki_index.py test/test_cli_data_dir.py
git commit -m "feat(cli): kb-wiki-index honors KB_DATA_DIR"
```

### Task 4: Wire `kb-lint-handoff` to `KB_DATA_DIR`

**Files:**
- Modify: `src/kb/cli/lint_handoff.py:192-214` (the `main()` function)
- Test: `test/test_cli_data_dir.py` (append)

- [ ] **Step 1: Write the failing test (append)**

```python
def test_lint_handoff_targets_kb_data_dir(tmp_path):
    # An empty handoffs/ dir lints clean (lint() returns early if absent/empty);
    # this proves the CLI resolved KB_DATA_DIR without touching the repo default.
    (tmp_path / "handoffs").mkdir(parents=True, exist_ok=True)
    proc = _run("kb.cli.lint_handoff", tmp_path)
    assert proc.returncode == 0
    assert "PASSED" in proc.stdout
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest test/test_cli_data_dir.py::test_lint_handoff_targets_kb_data_dir -v`
Expected: FAIL only if the repo's real `data/handoffs` has lint errors; otherwise it may pass for the wrong reason. To make the failure deterministic, the test relies on the next step's behavior — if unsure, temporarily assert the printed path. Proceed to Step 3.

- [ ] **Step 3: Wire `main()` to the resolver**

```python
# src/kb/cli/lint_handoff.py — replace main()
def main() -> None:
    from kb import data_dir

    parser = argparse.ArgumentParser(prog="kb-lint-handoff", description=__doc__)
    parser.add_argument(
        "--strict",
        action="store_true",
        help="treat warnings as errors (exit 1 on any warning)",
    )
    args = parser.parse_args()

    handoffs_dir = data_dir() / "handoffs"
    print(f"Linting {handoffs_dir}/...\n")

    result = LintResult()
    lint(result, handoffs_dir=handoffs_dir)
    result.print_report()

    if not result.ok:
        print("\nFAILED — fix errors before committing.")
        sys.exit(1)
    if args.strict and result.warnings:
        print("\nFAILED (--strict) — warnings treated as errors.")
        sys.exit(1)
    print("\nPASSED")
    sys.exit(0)
```

- [ ] **Step 4: Verify path resolution**

Add a path assertion to the test to make it deterministic:

```python
    assert str(tmp_path) in proc.stdout   # the printed "Linting <dir>/..." line
```

Run: `uv run pytest test/test_cli_data_dir.py::test_lint_handoff_targets_kb_data_dir -v`
Expected: PASS

- [ ] **Step 5: Run the full suite + lint, then commit**

Run: `uv run pytest test/test_cli_data_dir.py test/test_data_dir.py test/test_lint_wiki.py test/test_lint_handoff.py test/test_wiki_index.py -v`
Expected: all PASS (no regressions in the existing lint/index tests).

Run: `./scripts/lint.sh`
Expected: clean (this also confirms `scripts/lint.sh`, which calls the linters with no `KB_DATA_DIR`, still resolves the default `<repo>/data`).

```bash
git add src/kb/cli/lint_handoff.py test/test_cli_data_dir.py
git commit -m "feat(cli): kb-lint-handoff honors KB_DATA_DIR"
```

---

## Phase 2 — `data-sync` skill scaffold + setup scripts

### Task 5: Shared bash lib + `data-sync/SKILL.md`

**Files:**
- Create: `.claude/skills/data-sync/scripts/_lib.sh`
- Create: `.claude/skills/data-sync/SKILL.md`

- [ ] **Step 1: Write `_lib.sh` (sourced by all data-sync scripts)**

```bash
# .claude/skills/data-sync/scripts/_lib.sh
# Shared helpers for the data-sync scripts. Source, do not execute.
# Resolves KB_ROOT from the *caller's* location is unreliable; each script
# computes KB_ROOT and exports DATA before sourcing.

PRIVATE_REPO="yw0nam/PrivateKnowledgeBase"
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
  printf '%s' "$id" > "$idfile"
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
```

- [ ] **Step 2: Write `SKILL.md` (runtime contract)**

```markdown
---
name: data-sync
description: Use when syncing the nested data/ repo to its private remote — publishing the current work branch as a PR, installing the CI lint workflow, migrating data/ onto the work-branch model, or recovering from a cross-machine conflict. Owns sync-data.sh and the setup-data-*.sh scripts.
---

# data-sync

Runtime contract for syncing `data/` to `yw0nam/PrivateKnowledgeBase` via a
work-branch → PR → merge-commit model. Design doc: `docs/data-sync.md`.

## Invariants

- AI/cron sessions **commit only to the work branch** (`sync/<machine>-<date>-<rand>`), never to `master`.
- Push / PR / branch pruning happen **only in `sync-data.sh`** (shell, outside any AI session).
- Local `master` is never hand-committed; it only tracks `origin/master` via fetch.
- **A mandatory local lint gate runs before every push — `sync-data.sh` refuses to push if it fails.** Remote CI is the second, authoritative gate; bad data never leaves the machine.
- Merge method is **merge-commit**, enforced at the repo level (set in `setup-data-remote.sh`).
- GitHub Free private repos cannot enforce protected branches. Merge only through `merge-data-pr.sh`, which requires remote `lint=pass` and pins the reviewed head SHA.
- Privacy: every network path runs the origin allowlist guard; all `gh` calls pin `--repo yw0nam/PrivateKnowledgeBase`.

## Scripts

- `scripts/setup-data-remote.sh <git-url> [--dry-run]` — attach origin, set merge-method flags, initial push. (setup, user-run)
- `scripts/setup-data-ci.sh <pin> [--dry-run]` — install the CI lint workflow onto `origin/master`. Must run while `data/` is on `master`. (setup, user-run)
- `scripts/setup-data-workbranch.sh [--dry-run]` — migrate `data/` from `master` onto a work branch. (setup, user-run)
- `scripts/sync-data.sh [--dry-run]` — publish the work branch as a PR; prune merged branches; detect conflicts. (daily cron + manual)
- `scripts/merge-data-pr.sh` — wait for remote checks, require `lint=pass`, pin the reviewed head SHA, merge-commit. (user-run)

## Conflict handling (manual)

`sync-data.sh` never auto-resolves. On a non-mergeable PR or leftover cherry-pick
conflict it prints the file-class recipe and exits non-zero. Resolve by hand
in the live `data/` checkout, then re-run `sync-data.sh`. File classes:
`log.md` keep-both/sort-by-date · `wiki/**` union `sources:` · `handoffs/**`
keep newer `updated:` · `raw/**` conflict = immutability violation, investigate.
```

- [ ] **Step 3: Verify the skill is well-formed**

Run: `ls -la .claude/skills/data-sync/scripts/_lib.sh .claude/skills/data-sync/SKILL.md`
Expected: both exist.

- [ ] **Step 4: Commit**

```bash
git add .claude/skills/data-sync/SKILL.md .claude/skills/data-sync/scripts/_lib.sh
git commit -m "feat(data-sync): add skill contract and shared bash lib"
```

### Task 6: Move + harden `setup-data-remote.sh`

**Files:**
- Create: `.claude/skills/data-sync/scripts/setup-data-remote.sh`
- Delete: `scripts/setup-data-remote.sh`
- Test: `test/test_data_sync_scripts.py`

- [ ] **Step 1: Write the failing test**

```python
# test/test_data_sync_scripts.py
"""Subprocess tests for the data-sync bash scripts (guards, dry-run)."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import kb

SCRIPTS = kb.REPO_ROOT / ".claude" / "skills" / "data-sync" / "scripts"


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(cwd), *args], check=True,
                   capture_output=True, text=True)


def _make_data_repo(tmp_path: Path, origin_url: str | None = None) -> Path:
    """A bare-bones nested data/ repo on master."""
    data = tmp_path / "data"
    data.mkdir()
    _git(data, "init", "-q", "-b", "master")
    _git(data, "config", "user.email", "t@t")
    _git(data, "config", "user.name", "t")
    (data / "log.md").write_text("# log\n")
    _git(data, "add", "-A")
    _git(data, "commit", "-q", "-m", "init")
    if origin_url:
        _git(data, "remote", "add", "origin", origin_url)
    return data


def _run(script: str, data: Path, *args: str, **env_extra: str) -> subprocess.CompletedProcess:
    # Inherit the real env (git needs HOME/PATH etc.); override the data dir.
    env = dict(os.environ, KB_DATA_OVERRIDE=str(data), **env_extra)
    return subprocess.run(
        ["bash", str(SCRIPTS / script), *args],
        capture_output=True, text=True, env=env,
    )


def test_remote_refuses_non_private_origin(tmp_path):
    data = _make_data_repo(tmp_path, origin_url="https://github.com/yw0nam/KnowledgeBase.git")
    proc = _run("setup-data-remote.sh", data, "https://github.com/yw0nam/KnowledgeBase.git")
    assert proc.returncode != 0
    assert "not the allowed private remote" in (proc.stdout + proc.stderr)
```

> **Note for implementer:** the scripts locate `data/` as `$KB_ROOT/data` by default, but for testability they honor a `KB_DATA_OVERRIDE` env var pointing at a test `data/` dir. Add this override at the top of every script (after computing `KB_ROOT`): `DATA="${KB_DATA_OVERRIDE:-$KB_ROOT/data}"`.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest test/test_data_sync_scripts.py::test_remote_refuses_non_private_origin -v`
Expected: FAIL — `setup-data-remote.sh` does not yet exist in the skill dir.

- [ ] **Step 3: Write the moved + hardened script**

```bash
# .claude/skills/data-sync/scripts/setup-data-remote.sh
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
```

- [ ] **Step 4: Delete the old script + update references**

```bash
git rm scripts/setup-data-remote.sh
grep -rn "scripts/setup-data-remote.sh" docs/ .claude/ CHANGELOG.md
```

Note every hit for Task 14/15 (skill text + docs rewrite) — do not fix them here beyond confirming the list.

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest test/test_data_sync_scripts.py::test_remote_refuses_non_private_origin -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add .claude/skills/data-sync/scripts/setup-data-remote.sh test/test_data_sync_scripts.py
git rm scripts/setup-data-remote.sh
git commit -m "feat(data-sync): move setup-data-remote.sh into skill; enforce merge-commit"
```

### Task 7: `setup-data-workbranch.sh` (onboarding/migration)

**Files:**
- Create: `.claude/skills/data-sync/scripts/setup-data-workbranch.sh`
- Test: `test/test_data_sync_scripts.py` (append)

- [ ] **Step 1: Write the failing test**

```python
def test_workbranch_migrates_master_onto_workbranch(tmp_path):
    # remote (bare) + a clone on master ahead by 1 commit
    bare = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "master", str(bare)], check=True)
    data = _make_data_repo(tmp_path)
    _git(data, "remote", "add", "origin", str(bare))
    _git(data, "push", "-q", "-u", "origin", "master")
    # local master now 1 ahead of origin/master
    (data / "log.md").write_text("# log\nahead\n")
    _git(data, "commit", "-qam", "ahead")

    proc = _run("setup-data-workbranch.sh", data)
    assert proc.returncode == 0, proc.stderr
    head = subprocess.run(["git", "-C", str(data), "symbolic-ref", "--short", "HEAD"],
                          capture_output=True, text=True).stdout.strip()
    assert head.startswith("sync/")
    # local master mirrors origin/master (the ahead commit moved to the work branch)
    master = subprocess.run(["git", "-C", str(data), "rev-parse", "master"],
                            capture_output=True, text=True).stdout.strip()
    origin_master = subprocess.run(["git", "-C", str(data), "rev-parse", "origin/master"],
                                   capture_output=True, text=True).stdout.strip()
    assert master == origin_master
    # idempotent: a second run is a no-op (already on a work branch)
    proc2 = _run("setup-data-workbranch.sh", data)
    assert proc2.returncode == 0
    assert "already on a work branch" in (proc2.stdout + proc2.stderr)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest test/test_data_sync_scripts.py::test_workbranch_migrates_master_onto_workbranch -v`
Expected: FAIL — script missing.

- [ ] **Step 3: Write the script**

```bash
# .claude/skills/data-sync/scripts/setup-data-workbranch.sh
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

assert_private_origin "$DATA"

WB="$(new_work_branch "$DATA")"
run() { echo "+ $*"; [ "$DRY_RUN" = "--dry-run" ] || "$@"; }

# 2. fetch  3. cut work branch from current master HEAD (carries ahead commits)
run git -C "$DATA" fetch origin
run git -C "$DATA" checkout -b "$WB"
# 4. assert HEAD != master, then reset local master to origin/master
[ "$(git -C "$DATA" symbolic-ref --short HEAD)" != "master" ] || { echo "error: still on master" >&2; exit 1; }
run git -C "$DATA" branch -f master origin/master

echo "ok: data/ now on $WB; local master mirrors origin/master."
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest test/test_data_sync_scripts.py::test_workbranch_migrates_master_onto_workbranch -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/data-sync/scripts/setup-data-workbranch.sh test/test_data_sync_scripts.py
git commit -m "feat(data-sync): add setup-data-workbranch.sh migration"
```

### Task 8: CI template + `setup-data-ci.sh`

**Files:**
- Create: `.claude/skills/data-sync/reference/data-lint.yml`
- Create: `.claude/skills/data-sync/scripts/setup-data-ci.sh`
- Test: `test/test_data_sync_scripts.py` (append)

- [ ] **Step 1: Write the CI workflow template**

```yaml
# .claude/skills/data-sync/reference/data-lint.yml
# Installed into data/.github/workflows/lint.yml by setup-data-ci.sh.
# __KB_PIN__ is replaced by the installer with a tag/SHA of yw0nam/KnowledgeBase
# that INCLUDES the KB_DATA_DIR CLI change (spec §4.4).
name: data lint
on:
  pull_request:
    branches: [master]
jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - run: git fetch origin master
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - uses: astral-sh/setup-uv@v5
      - run: uv pip install --system "git+https://github.com/yw0nam/KnowledgeBase@__KB_PIN__"
      - name: lint
        env:
          KB_DATA_DIR: ${{ github.workspace }}
        run: |
          set -euo pipefail
          kb-wiki-index
          test -z "$(git status --porcelain -- wiki/INDEX.md)" \
            || { echo "INDEX.md out of date or untracked"; git status --porcelain -- wiki/INDEX.md; exit 1; }
          kb-lint-wiki
          kb-lint-handoff
          # raw immutability: only Added (A) allowed under raw/** vs the merge base.
          changed="$(git diff --diff-filter=acdmrtuxb --name-status -M origin/master...HEAD -- raw/)"
          if [ -n "$changed" ]; then
            echo "raw/** is immutable; non-addition changes found:"; echo "$changed"; exit 1
          fi
```

- [ ] **Step 2: Write the failing test**

```python
def test_ci_install_refuses_on_workbranch(tmp_path):
    data = _make_data_repo(tmp_path, origin_url="git@github.com:yw0nam/PrivateKnowledgeBase.git")
    _git(data, "checkout", "-q", "-b", "sync/host-2026-05-29-abcd")
    proc = _run("setup-data-ci.sh", data, "deadbeef", KB_SYNC_TEST="1")
    assert proc.returncode != 0
    blob = (proc.stdout + proc.stderr).lower()
    assert "must run on" in blob or "work branch" in blob


def test_ci_install_substitutes_pin_and_is_idempotent(tmp_path):
    bare = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "master", str(bare)], check=True)
    data = _make_data_repo(tmp_path)
    _git(data, "remote", "add", "origin", str(bare))
    _git(data, "push", "-q", "-u", "origin", "master")
    proc = _run("setup-data-ci.sh", data, "v1.2.3", KB_SYNC_TEST="1")
    assert proc.returncode == 0, proc.stderr
    wf = (data / ".github" / "workflows" / "lint.yml").read_text()
    assert "yw0nam/KnowledgeBase@v1.2.3" in wf
    assert "__KB_PIN__" not in wf
    # idempotent: second run no new commit
    proc2 = _run("setup-data-ci.sh", data, "v1.2.3", KB_SYNC_TEST="1")
    assert proc2.returncode == 0
    assert "no-op" in (proc2.stdout + proc2.stderr).lower()
```

> The allowlist guard would block a push to a non-private origin; the idempotency test's origin is a local bare repo (not the private URL). So `setup-data-ci.sh` skips the allowlist guard when `KB_SYNC_TEST=1` (test-only escape hatch, documented in `_lib.sh`). The tests pass it via `_run(..., KB_SYNC_TEST="1")` (the `**env_extra` kwarg added in Task 6's `_run`).

- [ ] **Step 3: Write the script**

```bash
# .claude/skills/data-sync/scripts/setup-data-ci.sh
#!/usr/bin/env bash
set -euo pipefail

# Install the CI lint workflow onto origin/master. Must run while data/ is on
# master (C4 — no throwaway worktree). Usage: bash setup-data-ci.sh <pin> [--dry-run]
#   <pin> = a tag or SHA of yw0nam/KnowledgeBase that includes the KB_DATA_DIR change.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KB_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
DATA="${KB_DATA_OVERRIDE:-$KB_ROOT/data}"
# shellcheck source=_lib.sh
source "$SCRIPT_DIR/_lib.sh"

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

[ "${KB_SYNC_TEST:-}" = "1" ] || assert_private_origin "$DATA"

run() { echo "+ $*"; [ "$DRY_RUN" = "--dry-run" ] || "$@"; }

# Base the commit on current origin/master (avoid non-ff from a stale master).
run git -C "$DATA" fetch origin
run git -C "$DATA" merge --ff-only origin/master

DEST="$DATA/.github/workflows"
mkdir -p "$DEST"
TMP="$(mktemp)"
sed "s|__KB_PIN__|$PIN|g" "$SCRIPT_DIR/../reference/data-lint.yml" > "$TMP"

if [ -f "$DEST/lint.yml" ] && cmp -s "$TMP" "$DEST/lint.yml"; then
  rm -f "$TMP"; echo "ok: lint.yml unchanged — no-op"; exit 0
fi
[ "$DRY_RUN" = "--dry-run" ] && { echo "+ install lint.yml (pin=$PIN)"; rm -f "$TMP"; exit 0; }
cp "$TMP" "$DEST/lint.yml"; rm -f "$TMP"

run git -C "$DATA" add .github/workflows/lint.yml
run git -C "$DATA" commit -m "ci: add data lint workflow"
run git -C "$DATA" push origin master   # NO force; on non-ff the user re-fetches and retries
echo "ok: CI lint workflow installed (pin=$PIN)."
```

- [ ] **Step 4: Add the `KB_SYNC_TEST` escape note to `_lib.sh`**

Append to `_lib.sh`:

```bash
# KB_SYNC_TEST=1 disables the network allowlist guard for hermetic tests that
# push to a local bare remote. Never set this outside the test suite.
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest test/test_data_sync_scripts.py -v`
Expected: all PASS (remote-guard, workbranch, ci-refuse, ci-idempotent).

- [ ] **Step 6: Commit**

```bash
git add .claude/skills/data-sync/scripts/setup-data-ci.sh .claude/skills/data-sync/reference/data-lint.yml .claude/skills/data-sync/scripts/_lib.sh test/test_data_sync_scripts.py
git commit -m "feat(data-sync): add CI workflow template and installer"
```

---

## Phase 3 — the sync helper

### Task 9: `sync-data.sh` — guards, lock, nothing-to-sync, dry-run

**Files:**
- Create: `.claude/skills/data-sync/scripts/sync-data.sh`
- Test: `test/test_data_sync_scripts.py` (append)

- [ ] **Step 1: Write the failing tests**

```python
def test_sync_refuses_on_master(tmp_path):
    data = _make_data_repo(tmp_path, origin_url="git@github.com:yw0nam/PrivateKnowledgeBase.git")
    proc = _run("sync-data.sh", data)
    assert proc.returncode != 0
    assert "work branch" in (proc.stdout + proc.stderr).lower()


def test_sync_refuses_non_private_origin(tmp_path):
    data = _make_data_repo(tmp_path, origin_url="https://github.com/yw0nam/KnowledgeBase.git")
    _git(data, "checkout", "-q", "-b", "sync/host-2026-05-29-abcd")
    proc = _run("sync-data.sh", data)
    assert proc.returncode != 0
    assert "not the allowed private remote" in (proc.stdout + proc.stderr)
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest test/test_data_sync_scripts.py -k sync_refuses -v`
Expected: FAIL — script missing.

- [ ] **Step 3: Write the guards + lock skeleton**

```bash
# .claude/skills/data-sync/scripts/sync-data.sh
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

DRY_RUN="${1:-}"
[ -z "$DRY_RUN" ] || [ "$DRY_RUN" = "--dry-run" ] || { echo "error: only --dry-run supported" >&2; exit 2; }
run() { echo "+ $*"; [ "$DRY_RUN" = "--dry-run" ] || "$@"; }

# Re-exec under flock on the canonical lock (shared with the cron wrapper) so
# no two syncs — or a sync and a cron commit — touch data/ at once.
LOCK="$DATA/$LOCK_FILE_REL"
if [ -z "${KB_SYNC_LOCKED:-}" ]; then
  exec env KB_SYNC_LOCKED=1 flock -n "$LOCK" "$0" "$@"
fi

# ── Guards ───────────────────────────────────────────────────────────
[ -d "$DATA/.git" ] || { echo "error: $DATA is not a git repo." >&2; exit 1; }
WB="$(git -C "$DATA" symbolic-ref --short HEAD)"
if [[ "$WB" != sync/* ]]; then
  echo "error: data/ is not on a work branch (HEAD=$WB). Run setup-data-workbranch.sh." >&2; exit 1
fi
[ "${KB_SYNC_TEST:-}" = "1" ] || assert_private_origin "$DATA"
if [ "${KB_SYNC_TEST:-}" != "1" ]; then
  gh auth status >/dev/null 2>&1 || { echo "error: gh not authenticated. Run: gh auth login" >&2; exit 1; }
fi

run git -C "$DATA" fetch origin

# (post-merge reconcile + push/PR added in Tasks 10–11)

# Nothing-to-sync: work branch not ahead of origin/master and no open PR.
AHEAD="$(git -C "$DATA" rev-list --count origin/master.."$WB" 2>/dev/null || echo 0)"
if [ "$AHEAD" = "0" ]; then
  echo "nothing to sync (work branch not ahead of origin/master)."; exit 0
fi
echo "TODO: push + PR (Task 10)"
```

> The lock `flock -n` is **non-blocking** (`-n`): a second concurrent sync exits immediately rather than queueing. The cron wrapper (Task 13) uses the **same** lock file `$DATA/.git/kb-sync.lock`.

- [ ] **Step 4: Run to verify the guard tests pass**

Run: `uv run pytest test/test_data_sync_scripts.py -k sync_refuses -v`
Expected: PASS (the lock re-exec must not interfere — `flock` is available on Linux CI; if a test runner lacks it, gate the lock behind `command -v flock`).

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/data-sync/scripts/sync-data.sh test/test_data_sync_scripts.py
git commit -m "feat(data-sync): sync-data.sh guards, lock, nothing-to-sync"
```

### Task 10: `sync-data.sh` — push + PR create/update

**Files:**
- Modify: `.claude/skills/data-sync/scripts/sync-data.sh`
- Test: `test/test_data_sync_scripts.py` (append)

**The local pre-flight lint is a MANDATORY blocking gate (spec §4.3 step 6 / §4.4):** the helper lints locally and **refuses to push if lint fails**. Remote CI is the second, authoritative gate — but we never push known-bad data. To keep this testable, the gate runs through a `preflight_lint()` function that the real script wires to the `uv run kb-*` commands, and which a test can override via `KB_SYNC_LINT_CMD` (so the gate is *exercised*, not skipped, in tests).

- [ ] **Step 1: Write two failing tests — the gate passes (push happens) and the gate fails (push blocked)**

```python
def test_sync_dry_run_plans_push_and_pr(tmp_path):
    bare = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "master", str(bare)], check=True)
    data = _make_data_repo(tmp_path)
    _git(data, "remote", "add", "origin", str(bare))
    _git(data, "push", "-q", "-u", "origin", "master")
    _git(data, "checkout", "-q", "-b", "sync/host-2026-05-29-abcd")
    (data / "log.md").write_text("# log\nmore\n")
    _git(data, "commit", "-qam", "more")
    # KB_SYNC_LINT_CMD="true" → the mandatory gate runs and passes (no real uv needed).
    proc = _run("sync-data.sh", data, "--dry-run", KB_SYNC_TEST="1", KB_SYNC_LINT_CMD="true")
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout
    assert "git" in out and "push" in out
    assert "gh pr" in out


def test_sync_blocks_push_when_local_lint_fails(tmp_path):
    """Mandatory local lint gate: a failing lint must abort BEFORE push/PR."""
    bare = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "master", str(bare)], check=True)
    data = _make_data_repo(tmp_path)
    _git(data, "remote", "add", "origin", str(bare))
    _git(data, "push", "-q", "-u", "origin", "master")
    _git(data, "checkout", "-q", "-b", "sync/host-2026-05-29-abcd")
    (data / "log.md").write_text("# log\nbad\n")
    _git(data, "commit", "-qam", "bad")
    # KB_SYNC_LINT_CMD="false" simulates a lint failure.
    proc = _run("sync-data.sh", data, KB_SYNC_TEST="1", KB_SYNC_LINT_CMD="false")
    assert proc.returncode != 0
    assert "lint" in (proc.stdout + proc.stderr).lower()
    assert "push" not in proc.stdout          # never reached the push step
    # the work branch was NOT pushed to the bare remote
    remote_heads = subprocess.run(["git", "-C", str(data), "ls-remote", "--heads", "origin"],
                                  capture_output=True, text=True).stdout
    assert "sync/host-2026-05-29-abcd" not in remote_heads
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest test/test_data_sync_scripts.py -k "dry_run_plans or blocks_push" -v`
Expected: FAIL — current script prints the `TODO: push + PR` line; no gate, no `gh pr`.

- [ ] **Step 3: Replace the TODO with the mandatory lint gate + push + PR**

Add the gate function near the top of `sync-data.sh` (after `source _lib.sh`):

```bash
# Mandatory pre-flight lint. Real run wires uv; tests override via KB_SYNC_LINT_CMD.
preflight_lint() {
  if [ -n "${KB_SYNC_LINT_CMD:-}" ]; then
    eval "$KB_SYNC_LINT_CMD"; return $?
  fi
  ( cd "$KB_ROOT" \
    && KB_DATA_DIR="$DATA" uv run kb-wiki-index \
    && [ -z "$(git -C "$DATA" status --porcelain -- wiki/INDEX.md)" ] \
    && KB_DATA_DIR="$DATA" uv run kb-lint-wiki --check-immutability \
    && KB_DATA_DIR="$DATA" uv run kb-lint-handoff )
}
```

Then replace the final `echo "TODO..."` block with:

```bash
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
if [ "${KB_SYNC_TEST:-}" = "1" ]; then
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
```

> Order is load-bearing: the lint gate is **before** the push. The `blocks_push` test asserts the push step is never reached on lint failure. In `--dry-run` the gate is described but not executed (it would write `INDEX.md`); a real run always executes it.

- [ ] **Step 4: Run to verify both tests pass**

Run: `uv run pytest test/test_data_sync_scripts.py -k "dry_run_plans or blocks_push" -v`
Expected: PASS (gate-passes → push planned; gate-fails → push blocked, branch not on remote).

- [ ] **Step 5: Document the lint-gate seam in `_lib.sh`**

Append to `_lib.sh`:

```bash
# KB_SYNC_LINT_CMD overrides the pre-flight lint command (tests only). The
# pre-flight lint is a MANDATORY gate — sync-data.sh refuses to push if it
# fails. Never set KB_SYNC_LINT_CMD outside the test suite.
```

- [ ] **Step 6: Commit**

```bash
git add .claude/skills/data-sync/scripts/sync-data.sh .claude/skills/data-sync/scripts/_lib.sh test/test_data_sync_scripts.py
git commit -m "feat(data-sync): mandatory local lint gate before push + PR"
```

### Task 11: `sync-data.sh` — post-merge reconcile + conflict detection

**Files:**
- Modify: `.claude/skills/data-sync/scripts/sync-data.sh`
- Test: `test/test_data_sync_scripts.py` (append)

- [ ] **Step 1: Write the failing test (merged → fresh branch cut, merged branch pruned)**

```python
def test_sync_reconcile_prunes_merged_branch(tmp_path):
    """Simulate: work branch's commits are already in origin/master (merged),
    leftover empty → sync cuts a fresh work branch and deletes the merged one."""
    bare = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "master", str(bare)], check=True)
    data = _make_data_repo(tmp_path)
    _git(data, "remote", "add", "origin", str(bare))
    _git(data, "push", "-q", "-u", "origin", "master")
    wb = "sync/host-2026-05-29-abcd"
    _git(data, "checkout", "-q", "-b", wb)
    (data / "log.md").write_text("# log\nx\n")
    _git(data, "commit", "-qam", "x")
    _git(data, "push", "-q", "-u", "origin", wb)
    # Merge wb into origin/master via a real merge-commit on the bare remote's master:
    _git(data, "checkout", "-q", "master")
    _git(data, "merge", "--no-ff", "-q", wb, "-m", f"Merge {wb}")
    _git(data, "push", "-q", "origin", "master")
    _git(data, "checkout", "-q", wb)
    # PR state is read from KB_SYNC_FAKE_PR_STATE in test mode (no gh call).
    proc = _run("sync-data.sh", data, KB_SYNC_TEST="1", KB_SYNC_FAKE_PR_STATE="MERGED")
    assert proc.returncode == 0, proc.stderr
    head = subprocess.run(["git", "-C", str(data), "symbolic-ref", "--short", "HEAD"],
                          capture_output=True, text=True).stdout.strip()
    assert head.startswith("sync/") and head != wb         # fresh branch cut
    branches = subprocess.run(["git", "-C", str(data), "branch", "--list", wb],
                              capture_output=True, text=True).stdout
    assert wb not in branches                               # merged branch pruned (local)
```

> The reconcile reads PR state via `gh pr view`. In `KB_SYNC_TEST=1` mode, read it from `KB_SYNC_FAKE_PR_STATE` instead of calling `gh`. Wire this in Step 3.

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest test/test_data_sync_scripts.py::test_sync_reconcile_prunes_merged_branch -v`
Expected: FAIL — no reconcile yet; the script tries to push an already-merged branch.

- [ ] **Step 3: Insert the reconcile block** (between `git fetch origin` and the nothing-to-sync check)

```bash
# ── Post-merge reconcile (commit-loss-safe) ─────────────────────────────
pr_state() {
  if [ "${KB_SYNC_TEST:-}" = "1" ]; then echo "${KB_SYNC_FAKE_PR_STATE:-OPEN}"; return; fi
  gh pr view "$WB" --repo "$PRIVATE_REPO" --json state -q .state 2>/dev/null || echo "NONE"
}
STATE="$(pr_state)"
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
    # Leftover = genuinely new commits after the synced push. Rebase onto a
    # fresh branch off origin/master; on conflict, abort + hand to the user.
    NEW="$(new_work_branch "$DATA")"
    run git -C "$DATA" checkout -b "$NEW" origin/master
    if ! git -C "$DATA" cherry-pick "origin/master..$WB" 2>/dev/null; then
      git -C "$DATA" cherry-pick --abort 2>/dev/null || true
      run git -C "$DATA" checkout "$WB"
      run git -C "$DATA" branch -D "$NEW"
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
fi
```

Add the conflict-help function near the top (after `source _lib.sh`):

```bash
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
```

- [ ] **Step 4: Run to verify the test passes**

Run: `uv run pytest test/test_data_sync_scripts.py::test_sync_reconcile_prunes_merged_branch -v`
Expected: PASS

- [ ] **Step 5: Run the whole script suite**

Run: `uv run pytest test/test_data_sync_scripts.py -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add .claude/skills/data-sync/scripts/sync-data.sh test/test_data_sync_scripts.py
git commit -m "feat(data-sync): sync-data.sh post-merge reconcile + conflict detect"
```

---

## Phase 4 — cron integration, skill text, docs

### Task 12: Cron wrapper — extend lock scope + call sync

**Files:**
- Modify: `scripts/cron/kb-cron-wrapup.sh`

- [ ] **Step 1: Read the current wrapper**

Run: `cat scripts/cron/kb-cron-wrapup.sh`
Confirm the structure: `flock -n "$LOCK_DIR/cron-wrapup.lock" bash -c '...claude...'` then a post-session log commit, then `exit $SESSION_EXIT`.

- [ ] **Step 2: Rewrite the locked region to include the log commit + sync**

The `flock` must wrap **session + log commit + sync** on the **same lock file** `data/.git/kb-sync.lock` that `sync-data.sh` uses (spec §4.6). Replace the body from the `flock` line through the log-commit block with:

```bash
SYNC="$KB_ROOT/.claude/skills/data-sync/scripts/sync-data.sh"
SESSION_EXIT=0
flock -n "$KB_ROOT/data/.git/kb-sync.lock" bash -c '
  set -uo pipefail
  KB_ROOT="$1"; PROMPT="$2"; TARGET_DATE="$3"; INFLIGHT_LOG="$4"
  ARCHIVE_LOG_DIR="$5"; ARCHIVE_REL="$6"; SYNC="$7"
  rc=0
  cd "$KB_ROOT"
  opencode run --model anthropic/claude-sonnet-4-6 --dangerously-skip-permissions \
    --dir "$KB_ROOT" "$PROMPT" >> "$INFLIGHT_LOG" 2>&1 || rc=$?

  # Archive + commit the run log on the work branch (post-session).
  mkdir -p "$ARCHIVE_LOG_DIR"
  cp "$INFLIGHT_LOG" "$ARCHIVE_LOG_DIR/$(basename "$ARCHIVE_REL")"
  git -C "$KB_ROOT/data" add "$ARCHIVE_REL" 2>/dev/null || true
  git -C "$KB_ROOT/data" diff --cached --quiet 2>/dev/null \
    || git -C "$KB_ROOT/data" commit -m "cron-wrapup-log: $TARGET_DATE" 2>/dev/null || true

  # Publish the day’s work as a PR (inside the same lock). Mark SYNC_SKIPPED in
  # the log if it cannot run, so the morning digest surfaces a silent machine.
  if [ -x "$SYNC" ]; then
    KB_SYNC_LOCKED=1 bash "$SYNC" >> "$INFLIGHT_LOG" 2>&1 \
      || echo "SYNC_SKIPPED: sync-data.sh exited non-zero" >> "$INFLIGHT_LOG"
  else
    echo "SYNC_SKIPPED: sync helper not found at $SYNC" >> "$INFLIGHT_LOG"
  fi
  exit $rc
' bash "$KB_ROOT" "$PROMPT" "$TARGET_DATE" "$INFLIGHT_LOG" "$ARCHIVE_LOG_DIR" \
  "raw/ops/cron/$(TZ=Asia/Seoul date -d "$TARGET_DATE" +%Y/%m)/${TARGET_DATE}_kb-cron-wrapup.log" \
  "$SYNC" || SESSION_EXIT=$?

exit $SESSION_EXIT
```

> `KB_SYNC_LOCKED=1` tells `sync-data.sh` it is already inside the `flock` (it must NOT re-exec a second `flock` on the same file — that would deadlock with `-n` and skip the sync). Confirm Task 9's re-exec guard checks `KB_SYNC_LOCKED`.

- [ ] **Step 3: Lint the shell**

Run: `bash -n scripts/cron/kb-cron-wrapup.sh`
Expected: no syntax errors. If `shellcheck` is installed: `shellcheck scripts/cron/kb-cron-wrapup.sh` (advisory).

- [ ] **Step 4: Commit**

```bash
git add scripts/cron/kb-cron-wrapup.sh
git commit -m "feat(cron): hold sync lock across session+log+sync; publish daily PR"
```

### Task 13: Skill text touch-ups

**Files:**
- Modify: `.claude/skills/knowledgebase-initialize/SKILL.md`
- Modify: `.claude/skills/cron-wrapup/SKILL.md`
- Modify: `.claude/skills/wiki-approval/SKILL.md`

- [ ] **Step 1: Find the push/path references to update**

Run:
```bash
grep -rn "setup-data-remote.sh\|docs/data-sync.md\|push" \
  .claude/skills/knowledgebase-initialize/SKILL.md \
  .claude/skills/cron-wrapup/SKILL.md \
  .claude/skills/wiki-approval/SKILL.md
```

- [ ] **Step 2: `knowledgebase-initialize` — add data-sync phases**

In Phase 2.5 (remote attach), change the script path to `.claude/skills/data-sync/scripts/setup-data-remote.sh` and add, in order:
- **Phase 2.6: Install Data CI Workflow** — run `setup-data-ci.sh <pin>` while `data/` is on `master` (before 2.7).
- **Phase 2.7: Check out work branch** — run `setup-data-workbranch.sh`.

Point all three at the `data-sync` skill as the runtime contract. (Match the file's existing phase-heading style; keep edits surgical.)

- [ ] **Step 3: `cron-wrapup` + `wiki-approval` — "push" → "push/PR"**

Where these SKILLs describe the deferred push action (`cron-wrapup/SKILL.md` ~lines 271/284/308; `wiki-approval/SKILL.md` ~line 76), change "push" → "push/PR (via the `data-sync` skill's `sync-data.sh`)" and replace the bare `docs/data-sync.md` pointer with the `data-sync` skill. No behavioral change to the commit instructions.

- [ ] **Step 4: Verify no stale path references remain**

Run: `grep -rn "scripts/setup-data-remote.sh" .claude/`
Expected: no hits (all updated to the skill path).

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/knowledgebase-initialize/SKILL.md .claude/skills/cron-wrapup/SKILL.md .claude/skills/wiki-approval/SKILL.md
git commit -m "docs(skills): point push/PR action at data-sync skill; add init CI/work-branch phases"
```

### Task 14: Rewrite `docs/data-sync.md` + CHANGELOG

**Files:**
- Modify: `docs/data-sync.md`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Read the current doc + its authoring rules**

Run: `cat docs/data-sync.md; echo '---'; sed -n '1,40p' docs/CLAUDE.md`
The doc must stay under the 200-line main-body rule (`docs/CLAUDE.md`); move edge cases to an Appendix.

- [ ] **Step 2: Rewrite the doc**

Rewrite `docs/data-sync.md` to describe the work-branch model as the **current** workflow (not future):
- **Synopsis / I/O**: work branch → PR → merge-commit; the `data-sync` skill is the runtime contract.
- **Daily workflow**: cron runs `sync-data.sh`; manual intra-day `bash .claude/skills/data-sync/scripts/sync-data.sh`.
- **Merge workflow**: after review, run `bash .claude/skills/data-sync/scripts/merge-data-pr.sh`; GitHub Free private repos cannot enforce branch protection server-side.
- **Setup (per machine)**: `setup-data-remote.sh` → `setup-data-ci.sh <pin>` (on master) → `setup-data-workbranch.sh`.
- **Conflict recovery**: the manual file-class recipe (mirror §9 / `_print_conflict_help`).
- **Appendix A**: GitHub Free private-repo limitation — UI merge and direct `master` push are prohibited bypasses because server-side branch protection requires a paid plan.
- Point at the `data-sync` skill and the new script paths throughout.
- Add a dated PatchNote to the Appendix (per `docs/CLAUDE.md`).

- [ ] **Step 3: Add the CHANGELOG entry**

Under `## Unreleased` → `### Added` / `### Changed` in `CHANGELOG.md`, add an operator-facing entry: the `data-sync` skill (sync-data.sh + setup-data-*.sh + CI template), the `KB_DATA_DIR` resolution for the three CLIs, the cron wrapper's daily PR + extended lock, the moved `setup-data-remote.sh`, and the `docs/data-sync.md` rewrite. One concise paragraph; no private data details.

- [ ] **Step 4: Verify doc length**

Run: `awk '/^## /{c++} c<=3 && /^/{n++} END{print n}' docs/data-sync.md` (rough) — or just confirm the main body (before Appendix) is under 200 lines by inspection.

- [ ] **Step 5: Commit**

```bash
git add docs/data-sync.md CHANGELOG.md
git commit -m "docs(data-sync): rewrite for work-branch PR model; changelog"
```

### Task 15: Full verification pass

**Files:** none (verification only)

- [ ] **Step 1: Python suite + lint**

Run: `uv run pytest test/ -q && ./scripts/lint.sh`
Expected: all tests PASS; lint clean.

- [ ] **Step 2: Shell syntax check all data-sync scripts**

Run: `for f in .claude/skills/data-sync/scripts/*.sh scripts/cron/kb-cron-wrapup.sh; do bash -n "$f" && echo "ok $f"; done`
Expected: `ok` for each.

- [ ] **Step 3: Dry-run the sync helper against a scratch repo**

Manually create a scratch `data/` (mirror `_make_data_repo` from the tests) on a work branch with one commit, then:
Run: `KB_DATA_OVERRIDE=/tmp/scratch-data KB_SYNC_TEST=1 bash .claude/skills/data-sync/scripts/sync-data.sh --dry-run`
Expected: prints planned `git push` + `gh pr create`, exit 0.

- [ ] **Step 4: Confirm the commit sequence**

Run: `git log --oneline main..HEAD`
Expected: the `KB_DATA_DIR` commits (Tasks 1–4) appear FIRST, before the skill/script/cron/docs commits.

### Task 16: Open PR + wire the CI pin (post-merge)

**Files:** none in this repo until the pin step.

- [ ] **Step 1: Open the PR to `main`**

Run: `gh pr create --base main --head worktree-feat+pr-base-data-sync --title "PR-based data/ sync (work-branch model)" --body "Implements docs/superpowers/specs/2026-05-29-pr-based-data-sync-design.md"`

- [ ] **Step 2: After review + merge, capture the merge SHA / tag**

Run: `git rev-parse origin/main` (the merge commit) — this is the `<pin>`. It includes the `KB_DATA_DIR` change (Tasks 1–4).

- [ ] **Step 3: Bootstrap CI into `data/` with the pin (per machine, on master)**

Run: `git -C data checkout master && bash .claude/skills/data-sync/scripts/setup-data-ci.sh <merge-sha>`
Then run `setup-data-workbranch.sh` to return `data/` to a work branch. (This is the per-machine setup, not a repo change.)

- [ ] **Step 4: Confirm CI fires on the next sync PR**

Trigger a sync (`bash .claude/skills/data-sync/scripts/sync-data.sh`), open the PR, and confirm the `data lint` check runs and passes on `yw0nam/PrivateKnowledgeBase`.

---

## Self-Review Notes

- **Spec coverage:** §4.0 skill (Task 5), §4.1 work branch + naming (Tasks 5/7), §4.2 merge-commit API enforce (Task 6), §4.3 sync helper + reconcile + manual conflict C1 (Tasks 9–11), §4.4 CI lint + KB_DATA_DIR prerequisite (Tasks 1–4, 8), §4.5 CI install C4 (Task 8), §4.6 lock (Tasks 9, 12), §4.8 migration C2 (Task 7), §5 privacy allowlist (Tasks 5/6/9), §6 merge policy (Task 6 + doc Appendix Task 14), §7 file changes (all), §9 error handling (Tasks 9–11), §10 testing (test files throughout).
- **Sequencing:** `KB_DATA_DIR` (Tasks 1–4) commits first so the CI pin (Task 16) can reference a commit that includes it.
- **Test approach:** bash scripts are tested via pytest+subprocess with `KB_DATA_OVERRIDE` (point at a scratch `data/`) and `KB_SYNC_TEST=1` (skip network/allowlist for hermetic local-bare-remote tests). These two env hooks are the only test-affordances added to production scripts; both are documented inline.
- **Known simplifications (spec §12 C1–C4):** no scripted conflict resolution, random branch suffix, repo-level merge enforcement, CI install refuses on a work branch. The plan does not reintroduce the removed machinery.
