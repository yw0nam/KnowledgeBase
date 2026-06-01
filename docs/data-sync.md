# data/ Private Remote Sync

Updated: 2026-05-29

## 1. Synopsis

- **Purpose**: Sync the nested `data/` git repo across machines via a private git remote, without ever exposing it to the outer repo's remote.
- **I/O**: `data/` rides a work branch `sync/<machine>-<date>-<rand>`; AI/cron commits land there; `sync-data.sh` runs a mandatory local lint gate then pushes and opens a PR against `master`; remote CI re-lints; the user runs `merge-data-pr.sh`; next sync prunes the merged branch and cuts a fresh one.
- **Runtime contract**: the `data-sync` skill (`.claude/skills/data-sync/SKILL.md`). This document is the design reference.

## 2. Core Logic

### Why work-branch + merge-commit

`master` is never hand-committed — it only advances via merge-commits from the remote. This keeps the branch graph legible and makes pruning safe (a merged work branch is always a proper ancestor of `master` after merge-commit, so `git branch -D` loses nothing). Repo-level merge-commit enforcement is set by `setup-data-remote.sh` via the GitHub API.

### Setup (per machine, in order)

All scripts live under `.claude/skills/data-sync/scripts/`.

This workflow supports GitHub Free private repositories. GitHub Free does not
provide protected branches for private repos, so CI enforcement lives in the
user-run `merge-data-pr.sh` helper rather than a server-side branch rule.

**Step 1 — Attach remote** (run while `data/` is on `master`):

```bash
bash .claude/skills/data-sync/scripts/setup-data-remote.sh <private-url>
```

Verifies `data/.git` exists, refuses dirty trees and conflicting origins, sets the GitHub merge-method flag to `merge` (disabling squash/rebase), and pushes `master` upstream. Idempotent on identical URLs.

**Step 2 — Install CI lint workflow** (run while `data/` is still on `master`):

```bash
bash .claude/skills/data-sync/scripts/setup-data-ci.sh <pin>
```

`<pin>` is a tag or SHA of the outer repo that includes the `KB_DATA_DIR` change. Commits the CI workflow file and pushes it **directly to `master`** on the remote (a direct push, not a PR — the workflow must exist on `master` before it can run on later PRs). No force-push. Must run on `master` before the work-branch checkout.

**Step 3 — Check out work branch**:

```bash
bash .claude/skills/data-sync/scripts/setup-data-workbranch.sh
```

Moves `data/` from `master` onto a `sync/<machine>-<date>-<rand>` branch. After this, AI/cron sessions commit only to work branches; they never commit to `master` directly.

### Daily workflow

- **Automated (cron)**: `kb-cron-wrapup.sh` runs `sync-data.sh` after its session commits, archives the sync result, then publishes the archived log commit too, inside the same `data/.git/kb-sync.lock`.
- **Manual intra-day**: `bash .claude/skills/data-sync/scripts/sync-data.sh`

`sync-data.sh` flow: fetch → detect merged/closed PR → reconcile or cut fresh branch → warn on dirty tree (non-blocking) → mandatory local lint → push → create/update PR.

After reviewing the PR, merge it through the free-plan merge gate:

```bash
bash .claude/skills/data-sync/scripts/merge-data-pr.sh
```

The helper waits for remote checks, requires the `lint` job to pass, verifies
that the PR is mergeable, and pins the reviewed head SHA during merge. Do not
merge through the GitHub UI or push directly to `master`: GitHub Free private
repos cannot block those bypasses server-side.

### Privacy guardrails

- Origin allowlist: only the configured private repo (SSH or HTTPS). Any other URL is refused before push.
- All `gh` calls pin `--repo <private-repo>`.
- Outer `.gitignore` excludes `data/`; `data/.git` is independent.
- AI/cron sessions never push. Only `sync-data.sh` (a shell script, not an AI session) pushes and opens PRs.

### Conflict handling

`sync-data.sh` never auto-resolves. On a non-mergeable PR or leftover cherry-pick conflict it prints the file-class recipe and exits non-zero. See Appendix A for the manual recovery steps.

### Lint gates

Two gates run on every sync:

1. **Local (blocking)**: `sync-data.sh` runs `kb-wiki-index`, `kb-lint-wiki --check-immutability`, `kb-lint-handoff`. Refuses to push on any failure.
2. **Remote CI**: the installed GitHub Actions workflow re-lints on every PR push. `merge-data-pr.sh` refuses to merge until its `lint` job passes.

## 3. Usage

| Need | Command |
|---|---|
| Attach private remote (Step 1) | `bash .claude/skills/data-sync/scripts/setup-data-remote.sh <url>` |
| Install CI workflow (Step 2) | `bash .claude/skills/data-sync/scripts/setup-data-ci.sh <pin>` |
| Check out work branch (Step 3) | `bash .claude/skills/data-sync/scripts/setup-data-workbranch.sh` |
| Manual sync (push + PR) | `bash .claude/skills/data-sync/scripts/sync-data.sh` |
| Merge reviewed PR after CI | `bash .claude/skills/data-sync/scripts/merge-data-pr.sh` |
| Dry-run (no network calls) | `bash .claude/skills/data-sync/scripts/sync-data.sh --dry-run` |
| Inspect current remote | `git -C data remote -v` |
| Change remote URL | `git -C data remote set-url origin <new-url>` |

---

## Appendix A — Conflict Recovery

When `sync-data.sh` exits non-zero with a conflict message, recover by hand:

```bash
# 1. Commit or stash any uncommitted in-session output first.
git -C data status

# 2. Rebase the work branch onto the updated master.
git -C data rebase origin/master
```

Resolve by file class:

| Path pattern | Resolution |
|---|---|
| `log.md` | Keep both sides; sort entries by date. |
| `wiki/**` | Union the `sources:` frontmatter arrays; manually merge prose. |
| `handoffs/**` | Keep the side with the newer `updated:` field; record the reason in the next handoff. |
| `raw/**` | Conflict = immutability violation. The same path was created with different content on two machines. Investigate which side is authentic before continuing. Do **not** push until resolved. |

```bash
# 3. After resolving all conflicts:
git -C data rebase --continue

# 4. Re-run sync (re-lints, then pushes).
bash .claude/skills/data-sync/scripts/sync-data.sh
```

## Appendix B — GitHub Free limitation

Protected branches for private repositories require a paid GitHub plan. On the
free plan, GitHub cannot prevent a user from bypassing `merge-data-pr.sh` via the
web UI or a direct push to `master`. Treat both as prohibited operator actions.

## Appendix C — State DB (`data/db/`)

`data/db/` is excluded by `data/.gitignore` and is not synced via git. The current memory workflow keeps markdown frontmatter as the source of truth; `state.db` is derivable per-machine. A future migration to "DB as source of truth" will require a separate sync mechanism (rsync, litestream, etc.).

## Appendix D — PatchNote

- 2026-06-01: Bootstrapped the reference machine onto the work-branch model and documented the existing-local-commits migration recipe (Appendix E). `merge-data-pr.sh` requires a modern `gh` (uses `gh pr checks --watch`, `gh pr view --json headRefOid`, `gh pr merge --match-head-commit`); these are unsupported on `gh` 2.4.0.
- 2026-06-01: Adapted merge enforcement for GitHub Free private repositories. Added `merge-data-pr.sh`; remote lint is verified by the supported merge helper because server-side protected branches require a paid plan.
- 2026-05-29: Rewrote for the work-branch → PR → merge-commit model. `setup-data-remote.sh` moved into the `data-sync` skill; added `setup-data-ci.sh` and `setup-data-workbranch.sh`; daily PR via `kb-cron-wrapup`; remote CI lint; mandatory local lint gate.
- 2026-05-28: Initial publication. Establishes private-remote model, conflict recovery guide, and future hook roadmap.

## Appendix E — Migrating a machine that already has local `data/` commits

Use when a machine's `data/` carries commits **ahead of `origin/master`** (on
`master` or a feature branch) and you are adopting the work-branch model.
`setup-data-workbranch.sh` alone is **not** enough here: if local `master` is
ahead, `setup-data-ci.sh` would push those data commits straight to `master`,
bypassing the PR/lint flow. The reset (step 2) **must** precede CI install (step 3).

Substitute `<WORK>` = the branch holding your commits, `<DATE>` = today, `<pin>`
= an outer-repo SHA that includes the `KB_DATA_DIR` change.

```bash
# 1. Back up the local commits (preserves everything; nothing below loses work).
git -C data fetch origin
git -C data branch backup/pre-sync-<DATE> <WORK>

# 2. Reset local master to the remote (commits are safe in the backup branch).
git -C data switch --detach origin/master
git -C data branch -f master origin/master
git -C data switch master

# 3. Remote policy + CI — the ONLY direct master pushes (run while on master).
bash .claude/skills/data-sync/scripts/setup-data-remote.sh <private-url>
bash .claude/skills/data-sync/scripts/setup-data-ci.sh <pin>

# 4. Replay the backed-up commits onto a fresh work branch.
#    cherry-pick stages them on master; setup-data-workbranch moves them to the
#    work branch and resets master back to origin/master.
git -C data cherry-pick origin/master..backup/pre-sync-<DATE>
bash .claude/skills/data-sync/scripts/setup-data-workbranch.sh

# 5. First PR → review → merge → reconcile onto a fresh work branch.
bash .claude/skills/data-sync/scripts/sync-data.sh
bash .claude/skills/data-sync/scripts/merge-data-pr.sh
bash .claude/skills/data-sync/scripts/sync-data.sh

# 6. After confirming origin/master is correct, delete the backup and old branch.
git -C data branch -D backup/pre-sync-<DATE> <WORK>
```
