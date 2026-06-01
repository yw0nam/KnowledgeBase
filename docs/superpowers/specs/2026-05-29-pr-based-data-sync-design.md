# PR-Based `data/` Sync — Design

Date: 2026-05-29
Status: Approved — hardened (R2: Git WM + codex) then simplified (R3: Karpathy simplicity audit, C1–C4). Ready for implementation planning. See §12 review log.
Scope: A only — PR-based `data/` git sync + remote CI lint. The Hermes-kanban → GitHub Issues/Projects migration (B) is a **separate, later spec** and is explicitly out of scope here.

## 1. Synopsis

- **Purpose**: Replace direct `git push origin master` of the nested `data/` repo with a branch → PR → **merge-commit** model on the existing private remote (`yw0nam/PrivateKnowledgeBase`), adding a remote CI lint gate, a review surface, and multi-machine conflict safety — without exposing `data/` to the outer repo's public remote.
- **I/O**: Local `data/` commits (from AI/cron sessions, made on a **daily work branch** — never on `master`) → **mandatory local lint gate (must pass before push)** → work branch pushed → PR against `master` → remote CI lint re-checks → `merge-data-pr.sh` verifies CI + pins the reviewed head SHA → merge-commit. `master` is never hand-committed locally; it only advances via PR merge on the remote. **Two lint gates: local (before push, blocking) + remote CI (checked by the merge helper).**
- **Drivers** (user-stated): clean history, multi-machine conflict safety, remote CI lint, review gate. (The longer-term motivation — removing the external Hermes-kanban dependency in favor of GitHub-native primitives — is satisfied by a later spec B; this spec only lays the GitHub branch/PR/CI foundation it will build on.)

## 2. Background / Current State

- `data/` is a nested private git repo, default branch `master` (on the remote), with private remote `origin = github.com/yw0nam/PrivateKnowledgeBase` (private). Outer repo `yw0nam/KnowledgeBase` is **public** (default `main`).
- **Today (the problem)**: AI sessions and cron jobs commit to local `master`, which accumulates ahead of `origin/master`; the user manually `git -C data push`es `master`. Because `master` is *both* the branch we keep committing to *and* the branch the remote integrates, once PRs/merges enter the picture, local `master` and `origin/master` diverge and tangle (esp. across multiple days/machines with an in-flight PR). **This design's core fix: never hand-commit local `master`; work lands on a separate branch from the start** (Option 1, §4.1).
- AI sessions/cron **never push** (CLAUDE.md hard rule). Skill contracts already delegate push to "the shell wrapper outside the AI session" (`cron-wrapup/SKILL.md:271,284,308`; `wiki-approval/SKILL.md:76`; `knowledgebase-initialize/SKILL.md:18`), pointing at `docs/data-sync.md`. **No skill changes its commit *command*; only the branch HEAD points at changes (work branch, not master), and the "push" slot becomes "open PR."**
- Which cron jobs commit to `data/`:
  - `cron-wrapup` — AI commits `cron-wrapup: DATE`; shell wrapper commits `cron-wrapup-log: DATE` post-session. Runs last (~05:00 KST).
  - `wiki-promote` — AI commits if pages were promoted.
  - `memory-daily/weekly/monthly` — **never commit** (contract: "Never run git commit"); output sits uncommitted for review.
  - daily-report jobs (claude-code/hermes/opencode), `wiki-ttl-sweep` — do not touch git.
- The private repo currently has **no CI workflow**. squash merge is allowed; we will use **merge commits** (see §4.2).
- **Skill structure** (verified): each workflow skill lives in `.claude/skills/<skill>/` with `SKILL.md` + a `reference/` folder (templates/reference docs); **no skill bundles executable scripts today**. cron shell wrappers live in `scripts/cron/kb-*.sh`; `setup-data-remote.sh` lives loose in `scripts/`. Skills already **import** one another (`memory-report` imports `wiki-authoring`/`handoff-document`; cron wrappers import `handoff-document`). This design introduces the first skill-bundled executable scripts under a new `data-sync` skill (see §4.0).

## 3. Goals & Non-Goals

**Goals**
1. A new self-contained **`data-sync` skill** that owns the whole sync lifecycle (remote attach, CI install, daily/manual PR, conflict recovery), with its scripts bundled in the skill folder.
2. A sync helper that publishes the current **work branch** as a PR on the private remote — runnable manually and from cron. Cross-machine conflicts are **detected and handed to the user** with guidance, not auto-resolved (C1).
3. Automatic daily PR via the `kb-cron-wrapup` shell wrapper (outside the AI session), delegating to the `data-sync` skill's script.
4. Remote CI lint on every PR to `master`, installed into the `data/` repo via the skill's installer script and wired into `knowledgebase-initialize`.
5. Privacy guardrails that make it impossible to accidentally push/PR `data/` to the outer or any public host.
6. Rewritten `docs/data-sync.md` (pointing at the `data-sync` skill as runtime contract) + `CHANGELOG.md` entry.

**Non-Goals (YAGNI)**
- Hermes-kanban → GitHub Issues/Projects migration (spec B).
- Server-side branch protection / `gh pr merge --auto` — unavailable for GitHub Free private repositories (§6).
- Session-start auto-pull hook.
- `data/db/` (state DB) sync.
- Committing memory jobs' uncommitted output (left to user review, as today).

## 4. Architecture

### 4.0 The `data-sync` skill (home for all sync logic)

A new self-contained workflow skill owns the entire `data/` sync lifecycle, mirroring how `cron-wrapup/SKILL.md` is the runtime contract for the wrap-up. `docs/data-sync.md` becomes its design doc; the skill is the runtime contract.

```
.claude/skills/data-sync/
├── SKILL.md                    # runtime contract: guards, sync procedure, conflict recovery, merge policy
├── scripts/
│   ├── sync-data.sh            # publish daily/manual PR (work-branch model)
│   ├── merge-data-pr.sh         # free-plan gate: require CI pass, then merge-commit
│   ├── setup-data-remote.sh    # MOVED from scripts/ (init-only, belongs to this workflow)
│   ├── setup-data-ci.sh        # install the CI workflow into data/
│   └── setup-data-workbranch.sh # one-time: migrate data/ from master onto a work branch
└── reference/
    └── data-lint.yml           # CI workflow template (source of truth)
```

- **Skill imports (consistent with existing pattern):**
  - `knowledgebase-initialize` imports `data-sync` for its setup phases (run `setup-data-remote.sh`, `setup-data-ci.sh`).
  - `kb-cron-wrapup.sh` (shell wrapper) calls `data-sync`'s `scripts/sync-data.sh` after the post-session log commit.
- **Manual invocation:** `bash .claude/skills/data-sync/scripts/sync-data.sh`, then `bash .claude/skills/data-sync/scripts/merge-data-pr.sh` after review (and `setup-data-*.sh` during init).
- The only shared exception kept loose is lint (`scripts/lint.sh`) and the cron launchers (`scripts/cron/kb-*.sh`), which are scheduler glue, not sync logic.

### 4.1 Git topology (Option 1 — `data/` rides a work branch; `master` stays clean)

| Element | Now | After |
|---|---|---|
| `data/` checkout | local `master` (accumulates commits) | **work branch** `sync/<machine>-<date>-<rand>`, cut from `origin/master` |
| AI/cron commit target | local `master` | the work branch (commit *command* unchanged — `git -C data commit`; only HEAD differs) |
| local `master` | committed to + pushed manually | **never hand-committed**; only tracks `origin/master` via fetch (not even checked out in `data/`) |
| Remote update | `git push origin master` | push work branch → PR → **merge-commit** into `origin/master` |
| Conflict handling | n/a | `sync-data.sh` **detects** non-mergeable and prints manual-resolution guidance (not scripted — §4.3) |

**Why this removes the tangle**: the work branch is the *only* place commits land locally; `origin/master` advances *only* via PR merge on the remote, and the local side just **fetches** it. Local `master` therefore can never diverge from `origin/master` — there is nothing local committed onto it to diverge. This is plain GitHub flow (feature branch → PR → main), applied to `data/`.

**Branch lifecycle**: a work branch persists until *its* PR merges (it keeps accumulating the day's commits and, if the PR is still open across a day boundary, the next day's too — keeping **one open PR at a time**). After merge, `sync-data.sh` cuts a **fresh** branch from the updated `origin/master` and deletes the merged one (local + remote) — but only once it is fully contained (§4.3 invariant).

**Branch naming**: `sync/<machine>-<date>-<rand>` (C2 — simplified; no managed counter).
- `<machine>` is a **sanitized, stable per-machine id** = `hostname` slugified + short random suffix, **minted once at init and persisted** to a git-ignored, machine-local file (`data/.sync-machine-id`, in `data/.gitignore`). Persisting it means a re-clone/re-init on the same physical machine reuses the id instead of minting a new one (which would orphan branches). Raw hostnames are rejected (they repeat across laptops and may contain ref-illegal characters; multi-machine safety depends on uniqueness).
- `<rand>` is a short random token (e.g. 4 hex chars) appended at cut time. This makes a same-machine, same-date re-cut (after a merge) collision-free **without** querying local+remote refs or maintaining a counter — the machine-id already guarantees cross-machine uniqueness, so `<rand>` only needs to disambiguate same-day re-cuts, which a random token does at negligible collision risk.

### 4.2 Why merge-commit (not squash)

Use **merge commits** for PRs. The work branch's individual commits become ancestors of `origin/master`, so the merged branch is fully contained in `origin/master` and the post-merge "cut a fresh branch from `origin/master`" step loses nothing. (Squash would collapse the commits into one, so the merged work branch would *not* be contained in `origin/master`, making the "fully landed?" check unreliable and pruning unsafe.) The containment check is `git log origin/master..<branch>` being empty (§4.3); merge-commit guarantees it becomes empty after merge. Individual commit history is preserved on `master`, which the user accepts.

**Enforced by a mechanism, not just convention** (the repo currently allows squash/rebase merge too): `setup-data-remote.sh` sets the repo merge settings via the GitHub API so the merge button *cannot* squash/rebase —
```sh
gh api -X PATCH repos/yw0nam/PrivateKnowledgeBase \
  -F allow_merge_commit=true -F allow_squash_merge=false -F allow_rebase_merge=false
```
This makes squash/rebase merges impossible at the source, so the §4.3 reconcile needs only a cheap local `merge-base --is-ancestor` assert rather than a per-run network check (C3), and §6's policy has an actual guardrail.

### 4.3 `data-sync/scripts/sync-data.sh` — sync helper

Idempotent; **at most one open sync PR at a time**. `data/` is already checked out on its work branch, so the happy path needs no worktree. Steps:

1. **Guards**:
   - `data/` and `data/.git` exist; `data/` HEAD is a `sync/<machine>-*` work branch (not `master`); else refuse with guidance.
   - `origin` resolves to the private remote. **Refuse** if the URL matches the outer repo or any public/disallowed host (privacy guard, §5).
   - `gh auth status` OK.
2. **Fetch**: `git -C data fetch origin`.
3. **Post-merge reconcile** (commit-loss-safe — do **not** gate on `branch --merged`, which misses commits added after the merged push):
   - Determine the work branch's PR state via `gh pr view <work-branch> --repo <private> --json state` → `state` ∈ {`OPEN`, `MERGED`, `CLOSED`}.
   - Compute **leftover** commits = `git -C data log origin/master..<work-branch>` (commits not yet in `origin/master`, regardless of PR state). This is the authoritative "what still needs to land" set.
   - Merge method is **merge-commit, enforced at the repo level** (`allow_squash_merge=false`/`allow_rebase_merge=false`, set in setup — §4.2). So a `MERGED` PR's branch tip is always an ancestor of `origin/master`. As a cheap assert (not a network call), the reconcile may verify `git -C data merge-base --is-ancestor <work-branch> origin/master` after a `MERGED` state before pruning; if it ever fails, refuse and require manual reconcile (signals the repo setting was bypassed).
   - `state == MERGED` **and** leftover empty → cut a fresh branch `sync/<machine>-<today>-<rand>` from `origin/master`, check it out in `data/`, delete the merged branch (local + remote).
   - `state == MERGED` **and** leftover non-empty (commits made after the last synced push) → **rebase leftover onto `origin/master`** on a fresh branch; continue with that as the new work branch (PR opened in step 8). If the rebase **conflicts**, `git rebase --abort`, print the manual-resolution guidance (§9), and exit non-zero — never leave `data/` mid-rebase. Nothing is discarded while `origin/master..<branch>` is non-empty.
   - `state == CLOSED` (closed, not merged) → leftover is non-empty by definition. **Do not auto-recreate the PR** (`gh pr create` on a closed-PR branch errors or reopens). Warn and require a manual decision: reopen the PR, or cut a fresh branch discarding the work. Exit non-zero.
   - **Invariant:** a branch is deleted only when `git log origin/master..<branch>` is empty (fully contained in `origin/master`).
4. **Dirty-tree warning**: if `data/` has uncommitted changes (e.g., memory-job output), **warn** that uncommitted work will NOT be in the PR; do **not** auto-commit. (Continue — only committed work syncs.)
5. **Nothing-to-sync check**: if the work branch is not ahead of `origin/master` and no open PR exists → print "nothing to sync", exit 0.
6. **Pre-flight lint — MANDATORY local gate; push is blocked on failure.** Local lint is **not** optional and **not** merely a convenience: the helper runs the full lint locally and verifies integrity **before** any push, and **refuses to push/PR if it fails** (§9). Remote CI is a *second, authoritative* line: it re-runs on the pinned linter for cross-machine consistency, and `merge-data-pr.sh` refuses the supported merge path unless it passes. The local gate is the *first* one and must pass first — we never push known-bad data and wait for CI to reject it. Run from the **outer repo root** (where the `uv` project lives), pointing `KB_DATA_DIR` at the `data/` work tree (an *absolute* path, to avoid the `data/data` trap if cwd ever changes):
   ```
   KB_DATA_DIR="$(pwd)/data" uv run kb-wiki-index    # then assert no INDEX change — see below
   KB_DATA_DIR="$(pwd)/data" uv run kb-lint-wiki --check-immutability
   KB_DATA_DIR="$(pwd)/data" uv run kb-lint-handoff
   ```
   - **Any non-zero exit here aborts the sync before step 7 (push). No push, no PR.**
   - INDEX freshness must be checked with `git -C data status --porcelain -- wiki/INDEX.md` being empty (not just `git diff --exit-code`) so a *regenerated-but-untracked* `INDEX.md` is also caught (§4.4).
   - `KB_DATA_DIR` is the **data tree root** (matching `src/kb/web/config.py`); the linters derive `wiki/`, `raw/`, `handoffs/` as children. The local pre-flight keeps the mtime-based `--check-immutability`; CI omits it (§4.4).
7. **Push**: `git -C data push -u origin <work-branch>`.
8. **PR (create or update)**: if a PR for the work branch is already open (`gh pr list --head <work-branch>`), the push already updated it — just print its URL. Else `gh pr create --repo yw0nam/PrivateKnowledgeBase --base master --head <work-branch>` with an auto-generated title/body summarizing `origin/master..HEAD`. Print the PR URL.
9. **Merge** is manual now (user reviews + merges on GitHub). Helper does not merge.

**Conflict path is manual (C1 — not scripted)**: when the work branch is not cleanly mergeable because `origin/master` moved (another machine merged first), `sync-data.sh` does **not** attempt to resolve. It **detects** the condition (the leftover cherry-pick in step 3 conflicts, or `gh pr view` reports the PR not mergeable), prints the file-class resolution guidance (§9), and exits non-zero. The user resolves by hand — consistent with the manual merge gate (the user is already reviewing/merging every PR on GitHub). This deliberately trades rare-case automation for a much smaller, safer script: auto-merging `data/` content by file class is the most error-prone logic in the design and is exercised only when multiple machines have overlapping in-flight changes. Recommended manual recipe is in §9; the user runs an ordinary `git -C data rebase origin/master`, resolves per file class, and re-runs `sync-data.sh`.

### 4.4 Remote CI lint

Remote CI is the **second** lint gate, not the only one. The **first** gate is the mandatory local pre-flight lint in `sync-data.sh` (§4.3 step 6), which blocks the push if it fails — bad data never leaves the machine. CI then re-runs the same checks on a *pinned* linter version (authoritative for cross-machine consistency); `merge-data-pr.sh` checks that result before merging. Both gates run the same logical checks; the local one gives fast feedback without burning a push/PR/CI cycle, the remote one is the source of truth for the supported merge path.

> **Prerequisite code change (verified against current code):** the CLI linters do **not** honor `KB_DATA_DIR` — `src/kb/cli/lint_wiki.py` and `wiki_index.py` hard-code `WIKI_DIR = REPO_ROOT/"data"/"wiki"` (only the web app reads `KB_DATA_DIR`). `lint_wiki.run()` already accepts `wiki_dir`/`raw_dir` params, so the change is small: make `kb-lint-wiki`, `kb-lint-handoff`, `kb-wiki-index` resolve their data dir from `KB_DATA_DIR` (falling back to the current default). Without this, CI lints the empty installed-package path, not the checkout. This is the one in-scope code change beyond scripts/skills.

A GitHub Actions workflow lives in the **`data/` repo** at `.github/workflows/lint.yml`, triggered on `pull_request` to `master`:

```
- checkout (PR branch) with fetch-depth: 0      # full history — base-ref diffs below need origin/master present
- git fetch origin master                        # ensure the merge-base ref exists for the diff
- setup Python 3.11 + uv
- uv pip install --system "git+https://github.com/yw0nam/KnowledgeBase@<pinned-tag-or-sha>"
- export KB_DATA_DIR=$GITHUB_WORKSPACE
- kb-wiki-index                                  # regenerate in place
- test -z "$(git status --porcelain -- wiki/INDEX.md)"   # INDEX up-to-date AND tracked (catches untracked regen)
- kb-lint-wiki                                   # schema/wikilink/sources (NO --check-immutability)
- kb-lint-handoff
- raw immutability (git-history based): no pre-existing raw/** file may change in any way but addition
    # fail on ANY status other than A (Added). -M flags renames as R (a rename = delete+add of a raw file ⇒ violation).
    git diff --diff-filter=adcmrtuxb --name-status -M origin/master...HEAD -- raw/   # must be empty
```

- **Linter source**: installed from the **public** outer repo (no secret). **Pinned** to a tag/SHA — and that pin **must include the `KB_DATA_DIR` prerequisite code change** (§7), else CI lints the installed package's default path, not the checkout. Bumped deliberately so CI rules don't drift from the local pre-flight linter.
- **Data dir**: `KB_DATA_DIR=$GITHUB_WORKSPACE` (the data repo root *is* the data dir), enabled by the prerequisite above.
- **INDEX gate uses `git status --porcelain`, not `git diff --exit-code`**: a PR that deletes the tracked `INDEX.md` would let `kb-wiki-index` recreate it as an *untracked* file — `git diff` (tracked-only) exits clean and `kb-lint-wiki` then sees the filesystem file and passes. `status --porcelain` is non-empty for untracked/regenerated files, closing that hole.
- **Raw immutability is git-based, not mtime-based** (verified: `check_raw_captured_at_mtime` errors when `mtime > captured_at + tol`; a fresh checkout sets every mtime to *now*, so `--check-immutability` would fail every historical raw file). CI omits `--check-immutability` and enforces raw immutability from git history: **only `A` (added) is allowed** under `raw/**` vs the merge base — modify/delete/**rename** (rename = delete+add of a supposedly-immutable raw file) all fail. The diff uses `origin/master...HEAD` (merge-base form), which is why `fetch-depth: 0` + the explicit base fetch are required. Local pre-flight keeps the mtime check.

### 4.5 CI install (`data-sync/scripts/setup-data-ci.sh`) + template

Because `data/` is a separate repo re-created per machine, the CI workflow must be **installed** into it:

- **Template** (single source of truth, readable YAML) is bundled in the skill: `.claude/skills/data-sync/reference/data-lint.yml`.
- **Installer** `data-sync/scripts/setup-data-ci.sh` (idempotent, mirrors `setup-data-remote.sh` style):
  1. Refuse if `data/` / `data/.git` missing. **Run the §5 origin allowlist guard** before any network op (the bootstrap pushes to `master`; it must obey the same privacy guard as `sync-data.sh`).
  2. **Refuse if `data/` HEAD is not `master`** (C4) — print the instruction to run CI install on `master` during init, before `setup-data-workbranch.sh`. This keeps the installer single-path (no throwaway worktree).
  3. `git -C data fetch origin`, then `git -C data merge --ff-only origin/master` (fast-forward local `master` to the remote tip so the bootstrap commit lands on current `origin/master`, avoiding a non-ff push from a stale local `master`).
  4. Copy `reference/data-lint.yml` (resolved relative to the script) → `.github/workflows/lint.yml`. If unchanged vs `origin/master` → no-op exit.
  5. Commit it (`ci: add data lint workflow`) on `master` and **`push origin master` with NO force**. On non-fast-forward → re-fetch, ff-only, retry; **never force-push `master`**.
- **Why a direct push to `master` (not a PR)**: GitHub only triggers a `pull_request` workflow when the workflow file already exists on the **base** branch. A PR that *introduces* `lint.yml` runs no lint. So the workflow must be bootstrapped onto `origin/master` out-of-band. This push touches **no `data/` content** (only `.github/workflows/`), so it does not violate data-review intent. It is a **one-time setup action run by the user** (or interactive init with explicit consent), never by an autonomous cron session.
- **Branch context (C4 — simplified)**: init runs in order remote (2.5) → CI (2.6) → work branch (2.7), so `setup-data-ci.sh` runs while `data/` is still on `master` — the natural path: commit on top of *freshly-fetched* `origin/master`, push. **If `data/` is already on a work branch** (re-run / already-migrated machine), `setup-data-ci.sh` **refuses with instructions** ("CI bootstrap must run on `master` during init; re-run before `setup-data-workbranch.sh`, or temporarily `git -C data checkout master` to install it") rather than scripting a throwaway `master` worktree. CI install is a once-per-machine setup step, so requiring it on `master` is a reasonable precondition, not a real limitation — and it removes the worktree machinery entirely.
- **Open-PR race**: bootstrapping is expected to run *before* the first sync PR exists (init ordering above), so the race is unusual; if a sync PR is already open, advancing `origin/master` simply moves the PR's base (PRs re-target a moving base) — acceptable, but the push must still **fail safe (no force)** rather than clobber.

### 4.6 Cron integration (skill-aware)

- **Trigger point**: `scripts/cron/kb-cron-wrapup.sh` — it runs last (~05:00), and already performs a post-session commit (`cron-wrapup-log`). **After** that commit (outside the AI session), the wrapper calls `.claude/skills/data-sync/scripts/sync-data.sh`. This publishes the whole day's committed work (cron-wrapup + any wiki-promote commits) as **one daily merge-commit PR**.
- **Locking (fix — current `flock` is too narrow, and the two locks must be the SAME object)**: today `flock` wraps only the `claude` invocation; the post-session log commit and the new sync run *after* the lock releases, so an overlapping cron could mutate the work branch mid-sync. The wrapper must hold the lock across **session + log commit + sync** (extend the `flock` scope). `sync-data.sh` also takes a repo-level lock (it can be invoked manually, concurrently with cron) — but **both must `flock` the same canonical lock file** `data/.git/kb-sync.lock`. If they used *different* lockfiles, a manual `sync-data.sh` (holding the sync lock) and the cron session's in-flight work-branch commit (holding only the cron lock) would **not** be mutually excluded. One named mutex serializes cron-session-commit, cron-sync, and manual-sync alike.
  - **Residual (documented, out of scope to fully close)**: a *manual* AI session committing to the work branch while a manual `sync-data.sh` runs is not covered by `flock` (the AI session doesn't take the lock). Mitigation: manual sync's dirty-tree/`status --porcelain` guards (§4.3 step 4, §9) catch in-flight uncommitted state; document that users should not hand-run a committing skill and a sync concurrently.
- **No behavioral change to the committing skills.** Their "commit locally, never push" contract is unchanged; "push handled by shell wrapper" already exists. `cron-wrapup`/`wiki-approval`/`knowledgebase-initialize` SKILL.md get a consistency touch-up: "push" → "push/PR" and a pointer to the new `data-sync` skill (replacing the bare `docs/data-sync.md` reference where it described the push action).
- Intra-day syncs: user runs `data-sync/scripts/sync-data.sh` manually.

### 4.7 Responsibility matrix (who does what)

**Invariant**: AI sessions (any skill loaded by a cron job) only ever **commit to the current work branch** in `data/` — never to `master`. Branch push, PR open, and the post-merge fresh-branch cut are done **exclusively by `sync-data.sh`**, which runs in the shell *outside* any AI session — triggered either by the `kb-cron-wrapup.sh` wrapper (daily) or by the user (manual). This preserves the "never push in session" rule and guarantees local `master` is never hand-committed.

**Table A — `data/` local commits (who commits, and to where)**

| Actor | Execution context | Commits? | Target branch | What it commits |
|---|---|---|---|---|
| `cron-wrapup` skill | AI session (in-session) | ✅ | work branch | `cron-wrapup: DATE` (wiki summary + handoff), after data lint passes |
| `kb-cron-wrapup.sh` wrapper | shell, post-session | ✅ | work branch | `cron-wrapup-log: DATE` (archives the run log) |
| `wiki-promote` skill | AI session (in-session) | ✅ (only if pages promoted) | work branch | promotion commit |
| `memory-daily/weekly/monthly` skill | AI session (in-session) | ❌ | — | nothing — output left **uncommitted** for user review |
| daily-report skills, `wiki-ttl-sweep` | AI session (in-session) | ❌ | — | no git activity |
| User (manual) | manual shell | ✅ (optional) | work branch | e.g. commits reviewed memory output before a manual sync |
| `sync-data.sh` | shell (cron wrapper or manual) | ❌ **never commits content** | — | only publishes/branches/prunes; the one exception is cutting an empty fresh work branch post-merge |
| anyone | — | 🚫 **never** | `master` | local `master` is never hand-committed |

**Table B — The sync action (push → PR → merge → fresh branch)**

| Step | Owner | Context | Notes |
|---|---|---|---|
| Decide to sync (trigger) | `kb-cron-wrapup.sh` wrapper **or** user | shell, outside AI | daily after the log commit; or manual intra-day |
| **Pre-flight lint (blocking gate)** | `sync-data.sh` | shell, outside AI | mandatory; **push is skipped if it fails**; CI re-runs authoritatively before merge |
| **Push** work branch | `sync-data.sh` | shell, outside AI | `git -C data push -u origin <work-branch>` |
| **Open/update PR** | `sync-data.sh` | shell, outside AI | `gh pr create --repo <private> --base master`; push updates an already-open PR |
| Run CI lint | GitHub Actions | remote | on `pull_request` to `master` |
| **Merge** (merge-commit) | User via `merge-data-pr.sh` | shell + GitHub | free-plan gate: wait for checks, require `lint=pass`, pin reviewed head SHA, run `gh pr merge --merge` (§6) |
| Post-merge: cut fresh work branch off `origin/master` + delete merged branch | `sync-data.sh` | shell, outside AI | next run, after fetch shows the branch merged |
| **Conflict resolution** (only if `origin/master` moved) | **User** (manual) | shell | `sync-data.sh` only *detects* + prints §9 guidance; user runs `git -C data rebase origin/master`, resolves by file class, re-runs sync (C1) |

**Table C — Setup scripts (one-time per machine)**

| Script | Owner skill | Who runs it | Commits to `data/`? | Pushes? |
|---|---|---|---|---|
| `setup-data-remote.sh` | `data-sync` | user / `knowledgebase-initialize` | ❌ | ✅ initial `push -u origin master`; also sets merge-method API flags (§4.2) |
| `setup-data-ci.sh` | `data-sync` | user / `knowledgebase-initialize` | ✅ `ci: add data lint workflow` (on top of `origin/master`) | ✅ `push origin master`, **no force** (must bootstrap `lint.yml` onto the base branch — §4.5) |
| `setup-data-workbranch.sh` | `data-sync` | user / `knowledgebase-initialize` | ❌ | ❌ |

### 4.8 Onboarding & migration onto the work-branch model

- **Fresh machine (via `knowledgebase-initialize`)**: after the data repo + remote exist, `setup-data-workbranch.sh` checks out a work branch — `git -C data checkout -B sync/<machine>-<date>-<rand> origin/master` — so `data/` starts on a work branch, not `master`.
- **Existing machine (currently on `master`, ahead of `origin/master`)**: one-time `setup-data-workbranch.sh`, in this **order** (the dirty-tree guard must run first, and `branch -f master` must run while HEAD is *not* `master`):
  1. **Refuse** if `data/` has uncommitted changes (let the user commit/stash first) — `checkout -b` would otherwise silently carry untracked/modified files onto the work branch.
  2. `git -C data fetch origin`; refuse if `origin` missing.
  3. Cut the work branch from current `master` HEAD: `git -C data checkout -b sync/<machine>-<date>-<rand>` (carries the ahead commits).
  4. Assert `HEAD != master`, then `git -C data branch -f master origin/master` (safe only because HEAD is now the work branch; fails with "cannot force update the current branch" otherwise). *(Verified: `branch -f master origin/master` fails while HEAD is `master`, succeeds once HEAD is the work branch.)*
  Result: `data/` on the work branch with the previously-ahead commits; local `master` mirrors `origin/master`.
- **Note (existing machine with pre-migration manual pushes)**: if local `master` was ahead by commits *already merged on the remote* by another machine, the work branch carries duplicates. No data loss — the first `sync-data.sh` run is then *expected* to report a non-mergeable PR and route to the manual conflict recipe (§9), which is normal, not an error.
- Idempotent: if `data/` is already on a `sync/<machine>-*` branch, no-op.

## 5. Privacy Guardrails

- **Allowlist, not denylist**: `sync-data.sh` / `setup-data-*.sh` refuse unless `data/`'s `origin` matches the expected private repo (`yw0nam/PrivateKnowledgeBase`) in **either** SSH (`git@github.com:...`) or HTTPS form. An allowlist can't be slipped by a new public host or an unanticipated URL form the way a denylist can.
- All `gh` calls pin `--repo yw0nam/PrivateKnowledgeBase`, preventing accidental PR creation against a public repo (e.g., if cwd inference picked the outer repo).
- The guard runs on **every network path**, including `setup-data-ci.sh`'s bootstrap `push origin master` (§4.5 step 1), `setup-data-remote.sh`'s merge-method API call, and `merge-data-pr.sh` — not just `sync-data.sh`.
- Outer `.gitignore` keeps excluding `data/` (unchanged).
- AI sessions still never push/PR; only the shell helper (outside the session) does.

## 6. Merge Policy on GitHub Free

- **Merge method is merge-commit, enforced at the repo level** (the §4.3/§4.1 containment + pruning logic depends on it): the repo currently allows squash/rebase too. Enforcement is a **mechanism, not just convention** — `setup-data-remote.sh` sets `allow_squash_merge=false`, `allow_rebase_merge=false`, `allow_merge_commit=true` via the GitHub API (§4.2), so the merge button cannot squash. As defense-in-depth: always merge via `gh pr merge --merge`; and pruning **refuses** to delete a branch unless `git log origin/master..<branch>` is empty. (With repo-level enforcement, no per-run merge-method verification network call is needed — §4.3 keeps only a cheap local `merge-base --is-ancestor` assert, C3.)
- **Supported merge path**: the user reviews each PR, then runs `merge-data-pr.sh`. The helper waits for remote checks, requires the `lint` job to pass, verifies mergeability, and uses `gh pr merge --merge --match-head-commit <reviewed-sha>`.
- **GitHub Free limitation**: private repositories cannot use protected branches. The web UI and direct pushes cannot be blocked server-side, so both are prohibited operator bypasses. A paid GitHub plan could move this enforcement to branch protection later.

## 7. Components & File Changes

**New — `data-sync` skill (self-contained)**
- `.claude/skills/data-sync/SKILL.md` — runtime contract (guards, sync procedure, conflict recovery, merge policy, privacy invariants).
- `.claude/skills/data-sync/scripts/sync-data.sh` — sync helper (idempotent, guarded; detects conflicts and hands to user — C1, no worktree automation).
- `.claude/skills/data-sync/scripts/merge-data-pr.sh` — free-plan merge gate (remote lint pass + mergeability + reviewed-head pin).
- `.claude/skills/data-sync/scripts/setup-data-ci.sh` — CI workflow installer into `data/`.
- `.claude/skills/data-sync/scripts/setup-data-workbranch.sh` — one-time onboarding/migration of `data/` onto a work branch (§4.8).
- `.claude/skills/data-sync/reference/data-lint.yml` — CI workflow template (source of truth).

**Code (in-scope prerequisite)**
- `src/kb/cli/lint_wiki.py`, `lint_handoff.py`, `wiki_index.py` — resolve the data dir from `KB_DATA_DIR` (fallback to the current `REPO_ROOT/data` default). `lint_wiki.run()` already has the `wiki_dir`/`raw_dir` seam; wire the env in `main()`. Required for CI (and lets pre-flight lint target a path).
  - **Web-app safety (codex-confirmed)**: `src/kb/web/config.py` already treats `KB_DATA_DIR` as the data-tree root and falls back to `REPO_ROOT/data`; making the CLIs use the *same* semantics is consistent, not breaking. **Behavior-change to flag**: shell callers that already `export KB_DATA_DIR` for `kb-web` will now also retarget the CLIs (intended). `scripts/lint.sh` invokes the linters with no env/path today → confirm it still resolves the default. **Recommend this CLI change ships as its own small PR with tests** (it alters shared command behavior for all callers), landed and tagged *before* the CI pin references it (§4.4).

**Moved**
- `scripts/setup-data-remote.sh` → `.claude/skills/data-sync/scripts/setup-data-remote.sh` (belongs to the sync workflow). It still performs the initial `push` — keep that, but document/treat it (and the CI bootstrap push) as a **user/setup action**, never run by an autonomous cron session. Update all references.

**Modified**
- `scripts/cron/kb-cron-wrapup.sh` — after the post-session log commit, call `.claude/skills/data-sync/scripts/sync-data.sh`.
- `.claude/skills/knowledgebase-initialize/SKILL.md` — Phase 2.5 now imports the `data-sync` skill; new **Phase 2.6: Install Data CI Workflow** (run `setup-data-ci.sh`, ordered before the remote push in 2.5) and **Phase 2.7: Check out work branch** (`setup-data-workbranch.sh`) + updated paths/instructions. Also fix the `scripts/setup-data-remote.sh` path reference (line ~105).
- `.claude/skills/cron-wrapup/SKILL.md`, `wiki-approval/SKILL.md`, `knowledgebase-initialize/SKILL.md` — "push" → "push/PR" wording; point the push/PR action at the `data-sync` skill (no behavior change).
- `docs/data-sync.md` — rewrite Daily workflow, Conflict recovery, Usage table, and Appendix A (the "future automated sync" becomes current); add CI-setup section; point at the `data-sync` skill as runtime contract and the new script paths.
- `CHANGELOG.md` — outer-repo entry (new skill, moved script, CI template, cron wrapper, skill text, docs).

**Created in `data/` repo (setup action, not outer repo)**
- `data/.github/workflows/lint.yml` (via installer) + `data/.gitignore` entry for `.sync-machine-id` (the persisted per-machine id, §4.1). (No `.sync-worktrees/` — C1 removed the worktree path.)

## 8. Data Flow (daily happy path)

Precondition: `data/` is on work branch `sync/dev43-DATE` (cut from `origin/master`).

1. During the day: `wiki-promote` (and others) commit to the work branch; memory jobs leave output uncommitted.
2. 05:00 `kb-cron-wrapup.sh`: AI session writes wrap-up + commits `cron-wrapup: DATE` (work branch); shell commits `cron-wrapup-log: DATE` (work branch).
3. Shell calls `sync-data.sh`: guards → fetch → post-merge reconcile (no-op if nothing merged) → warn if dirty → pre-flight lint → `git -C data push -u origin sync/dev43-DATE` → `gh pr create --base master` (or no-op if PR already open).
4. GitHub Actions runs `lint.yml` on the PR.
5. User reviews, then runs `merge-data-pr.sh`; the helper requires remote `lint=pass`, pins the reviewed head SHA, and merges with a merge-commit.
6. Next `sync-data.sh` run: fetch sees the work branch merged into `origin/master` → cut fresh `sync/dev43-<newDATE>` from `origin/master`, check it out in `data/`, delete the merged branch (local + remote). Local `master` ref just tracks `origin/master`; it was never hand-committed, so nothing to reconcile.

## 9. Error Handling

- **`data/` not on a work branch** (e.g., still on `master`) → instruct running `setup-data-workbranch.sh`; exit non-zero.
- **No remote configured** → helper instructs running `setup-data-remote.sh`; exit non-zero.
- **Private-remote guard fails** (outer/public URL) → refuse, exit non-zero, no network call.
- **`gh` unauth** → instruct `gh auth login`; exit non-zero.
- **Pre-flight lint fails (mandatory local gate)** → **do not push/PR**; print the lint failures; exit non-zero. This is a hard stop, not advisory — bad data never leaves the machine. Fix locally (commit the fix to the work branch), then re-run the helper. (CI would reject it too, but we don't burn a push/PR/CI cycle to discover what the local lint already knows.)
- **PR not cleanly mergeable / leftover cherry-pick conflict** (`origin/master` moved — C1, manual) → `sync-data.sh` does **not** force-push or auto-resolve. It aborts the post-merge cherry-pick cleanly, leaves `data/` on its work branch untouched, prints the manual recipe, and exits non-zero. **Manual recipe** the user follows in the live `data/` checkout (commit/stash any in-session output first):
  ```
  git -C data rebase origin/master      # resolve conflicts by file class, then:
  #   log.md       → keep both, sort by date
  #   wiki/**      → union the sources: arrays
  #   handoffs/**  → keep the newer updated:
  #   raw/**       → conflict = immutability violation; investigate authenticity, do NOT just accept
  git -C data rebase --continue
  bash .claude/skills/data-sync/scripts/sync-data.sh   # re-run; push now fast-forwards the PR
  ```
- **PR closed but not merged** → do not auto-recreate the PR; warn and require a manual decision (reopen, or cut fresh discarding the work); exit non-zero (§4.3 `CLOSED` arm).
- **Un-pushed commits beyond a merged (merge-commit) branch** (post-merge reconcile) → cherry-pick them onto a fresh branch from `origin/master`; if that cherry-pick conflicts, fall to the manual recipe above; never discard (§4.3 invariant).
- **CI-bootstrap push non-fast-forward** (`setup-data-ci.sh`) → re-fetch `origin/master`, re-base the bootstrap commit, retry; **never force `master`** (§4.5).
- **`setup-data-ci.sh` run while `data/` is on a work branch** → refuse with instructions to run it on `master` during init (C4); exit non-zero.
- **PR already open** → push updates it; do not open a second PR.
- **CI red** → user does not merge; fix locally (commit to work branch), re-run helper to update the PR.
- **`sync-data.sh` invoked by cron but no remote / not on work branch** → emit a `SYNC_SKIPPED: <reason>` marker into the committed cron-wrapup log and exit non-zero so the failure is visible both to the scheduler and the morning digest.

## 10. Testing / Verification

- `sync-data.sh --dry-run` prints planned git/gh commands without executing (mirrors `setup-data-remote.sh --dry-run`).
- Guard unit checks: origin-not-on-allowlist refusal (non-private URL, both SSH/HTTPS); missing-remote refusal; unauth refusal; `data/`-on-`master` refusal.
- **Reconcile arms**: (a) MERGED + leftover empty → fresh branch cut, merged branch deleted; (b) MERGED + leftover non-empty → leftover cherry-picked, no duplication; (c) leftover cherry-pick **conflict → clean abort + non-zero + guidance printed**, `data/` left on its work branch untouched (C1); (d) **CLOSED-not-merged → refusal**, no second PR opened.
- **Branch identity**: machine-id persists across a simulated re-init (same `data/.sync-machine-id` reused); two same-machine same-date cuts produce distinct `<rand>` suffixes (no collision).
- **Locking**: a manual `sync-data.sh` and a held cron-scope `flock` on `data/.git/kb-sync.lock` are mutually exclusive (second blocks).
- `setup-data-workbranch.sh`: from a `master`-with-N-ahead `data/`, leaves `data/` on `sync/<machine>-<date>-<rand>` carrying the N commits with local `master` reset to `origin/master`; idempotent (no-op when already on a work branch).
- `setup-data-ci.sh`: idempotency (second run no-op); bootstrap commits on top of freshly-fetched `origin/master`; non-fast-forward push retries, never forces; **refuses when `data/` is on a work branch** (C4).
- `setup-data-remote.sh`: sets repo merge-method API flags (squash/rebase disabled) — assert via `gh api repos/...`.
- End-to-end manual: from `data/` on a work branch with N commits, run helper → PR created, CI triggers, merge (merge-commit) → next run cuts a fresh work branch and deletes the merged one; local `master` never diverges.
- Existing `./scripts/lint.sh` stays green for any Python touched; **`kb-web` regression**: with `KB_DATA_DIR` set, the three CLIs and the web app resolve the *same* data root (codex-confirmed config compatibility).

## 11. Open Implementation Questions (resolve in plan, not blocking)

Resolved during review (verified against code):
- **Data-dir**: CLI linters hard-code `REPO_ROOT/data`; they do **not** read `KB_DATA_DIR`. → covered by the §7 prerequisite code change. `KB_DATA_DIR` means the **data tree root** (matching `src/kb/web/config.py`), with the linters deriving `wiki/`/`raw/`/`handoffs/` as children and falling back to `REPO_ROOT/data`. All examples use an absolute path to avoid the `data/data` trap (§4.3 step 6).
- **`kb-wiki-index --check`**: no such mode; `main()` takes no args and writes in place. → CI/pre-flight run-then-`git status --porcelain -- wiki/INDEX.md`-empty (catches untracked regen too — §4.4).
- **CI immutability**: mtime-based `--check-immutability` fails on fresh checkout; CI uses git-history raw-diff (only `A` allowed; `fetch-depth: 0` + base fetch required) instead (§4.4).
- **Squash-merge unsafe rebase**: closed by repo-level merge-commit enforcement via API (§4.2); the runtime keeps only a cheap local `merge-base --is-ancestor` assert (C3).
- **Branch identity**: machine-id minted once at init and persisted to git-ignored `data/.sync-machine-id`; `<rand>` short random suffix appended at cut time — no managed counter (C2, §4.1).
- **Locking**: cron-wrapper `flock` and `sync-data.sh` use the *same* named lock `data/.git/kb-sync.lock` (§4.6).
- **Conflict resolution**: manual, user-driven with printed guidance — no scripted worktree/rebase/force-push (C1, §4.3/§9). This removed the trickiest script logic and the `.sync-worktrees/` open question entirely.

Remaining (genuinely defer-safe, not blocking):
1. PR body content: commit-range summary format (default: `git log origin/master..HEAD --oneline`).
2. Exact length/charset of `<rand>` (default: 4 hex chars from `openssl rand` / `/dev/urandom`).

## 12. Review Log

**Round 2 — final pre-implementation review (2026-05-29).** Adversarial pass by Git Workflow Master (git-correctness, scratch-verified) + codex (design soundness / scope / CI). One true blocker and several should-fix correctness gaps were found and folded into the spec above:

| Finding | Resolution | Section |
|---|---|---|
| **BLOCKER** — squash/rebase merge makes the "rebase leftover" arm resurrect already-landed content | Gate rebase on merge-commit verification (`merge-base --is-ancestor tip mergeCommit`) + enforce `allow_squash_merge=false`/`allow_rebase_merge=false` via API in setup | §4.2, §4.3, §6 |
| Branch identity / `<seq>` unresolved (codex: blocks scripts) | machine-id persisted to `data/.sync-machine-id`; `<seq>` = 1 + max over local **and** remote refs | §4.1, §11 |
| CI raw immutability: missing base fetch, misses renames | `fetch-depth: 0` + explicit fetch; allow only status `A` (rename ⇒ violation) | §4.4 |
| CI INDEX gate misses untracked regen | `git status --porcelain -- wiki/INDEX.md` instead of `git diff --exit-code` | §4.4 |
| Reconcile rebase / CLOSED-PR / force-push races | conflict→abort+worktree; `CLOSED` arm refuses; re-check `state==OPEN` + explicit-oid lease; `--porcelain` dirty guard | §4.3, §9 |
| CI bootstrap non-ff / clobber risk | commit on freshly-fetched `origin/master`, push no-force, privacy guard, worktree cleanup trap | §4.5, §5 |
| Two-lock gap | single named lock `data/.git/kb-sync.lock` for cron + manual sync | §4.6 |
| `KB_DATA_DIR` web-app safety | codex-confirmed compatible (web already treats it as data root); ship CLI change as its own tested PR | §7 |

**Scope / PR boundaries** — codex suggested splitting the work into ~5 separable PRs. **Rejected as over-engineered for this solo worktree repo**: all outer-repo changes (the `KB_DATA_DIR` CLI prerequisite, the `data-sync` skill + scripts, CI template, cron-wrapper locking, skill-text/docs) form **one coherent feature and ship as one outer-repo PR**. The `data/`-repo changes (installing `lint.yml`, work-branch migration) are **per-machine setup actions, not PRs** at all. The one *real* constraint codex surfaced is an **ordering dependency, not a PR boundary**: the CI lint installs the linter from a pinned commit of the public outer repo, so that pin must reference a commit that already contains the `KB_DATA_DIR` change. Satisfy it *within* the single PR: implement the `KB_DATA_DIR` CLI change as the **first commit(s)**, land the PR to `main`, then point the CI pin at the merge SHA (or a tag on it). No separate PR needed. The implementation plan sequences commits in this order; it does not multiply PRs.

**Round 3 — simplicity audit (Karpathy guidelines, 2026-05-29).** Round 2's adversarial hardening added defensive machinery that is over-engineered for a 1–3 machine personal KB. Four simplifications were adopted (user-approved), **superseding the corresponding Round 2 resolutions above**:

| ID | Cut | Supersedes | Net effect |
|---|---|---|---|
| **C1** | Conflict resolution is **manual** — `sync-data.sh` detects non-mergeable / leftover cherry-pick conflict, prints the §9 file-class recipe, exits non-zero; the user resolves by hand (consistent with the manual merge gate). | R2 "Reconcile rebase / force-push races" row, the §4.3 worktree path, `.sync-worktrees/` | Removes the most bug-prone, rarely-exercised code: scripted rebase, `--force-with-lease`, PR-state recheck, `reset --hard` adoption, worktree lifecycle. |
| **C2** | Branch name uses a short random `<rand>` suffix, not a managed `<seq>` counter. | R2 "Branch identity / `<seq>`" local+remote-max derivation | Removes ref-counting over local + `ls-remote`. machine-id still guarantees cross-machine uniqueness. |
| **C3** | Rely on **repo-level** merge-commit enforcement (API in setup); demote the runtime merge-method check to a cheap local `merge-base --is-ancestor` assert. | R2 BLOCKER's per-run `gh pr view mergeCommit` verification | Squash is impossible at the repo level, so the runtime network check guarded an unreachable state. |
| **C4** | `setup-data-ci.sh` **refuses** when `data/` is on a work branch (run it on `master` during init) instead of scripting a throwaway `master` worktree. | R2 "CI bootstrap … worktree cleanup trap" | Removes the throwaway-worktree path; CI install is a once-per-machine init step where `master` is the natural branch. |

**Verdict after Round 3: ready for implementation planning.** Core model (work branch, `master` never hand-committed, leftover-never-discarded, privacy allowlist, CI lint, `KB_DATA_DIR`) intact; the failure-prone edge automation is replaced by detect-and-guide. Remaining §11 items are defer-safe defaults.
