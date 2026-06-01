---
name: data-sync
description: Use when syncing the nested data/ repo to its private remote — publishing or merging the current work-branch PR, installing the CI lint workflow, migrating data/ onto the work-branch model, or recovering from a cross-machine conflict. Owns sync-data.sh, merge-data-pr.sh, and the setup-data-*.sh scripts.
---

# data-sync

Runtime contract for syncing `data/` to its private remote — whatever `data/`'s
own `origin` points at, set when the user clones or attaches their private repo
at init (no repo is hardcoded) — via a work-branch → PR → merge-commit model.
Design doc: `docs/data-sync.md`.

## Invariants

- AI/cron sessions **commit only to the work branch** (`sync/<machine>-<date>-<rand>`), never to `master`.
- Push / PR / branch pruning happen **only in `sync-data.sh`** (shell, outside any AI session).
- Local `master` is never hand-committed; it only tracks `origin/master` via fetch.
- **A mandatory local lint gate runs before every push — `sync-data.sh` refuses to push if it fails.** Remote CI is the second, authoritative gate; bad data never leaves the machine.
- Merge method is **merge-commit**, enforced at the repo level (set in `setup-data-remote.sh`).
- GitHub Free private repos cannot enforce branch protection. Merge only through `merge-data-pr.sh`, which requires the remote `lint` check to pass and pins the reviewed head SHA.
- Privacy: every network path runs the origin guard (`assert_private_origin` — origin must be a `github.com` remote, else refuse); all `gh` calls pin `--repo "$PRIVATE_REPO"`, the `owner/name` derived from `data/`'s own origin.

## Scripts

- `scripts/setup-data-remote.sh <git-url> [--dry-run]` — attach origin, set merge-method flags, initial push. (setup, user-run)
- `scripts/setup-data-ci.sh <pin> [--dry-run]` — install or update the CI lint workflow onto `origin/master`. Must run while `data/` is on `master`. (setup, user-run)
- `scripts/setup-data-workbranch.sh [--dry-run]` — migrate `data/` from `master` onto a work branch. (setup, user-run)
- `scripts/sync-data.sh [--dry-run]` — publish the work branch as a PR; prune merged branches; detect conflicts. (daily cron + manual)
- `scripts/merge-data-pr.sh` — wait for remote checks, require `lint=pass`, then merge the current PR with `--merge --match-head-commit`. This is the only supported merge path. (user-run)

## Conflict handling (manual)

`sync-data.sh` never auto-resolves. On a non-mergeable PR or leftover cherry-pick
conflict it prints the file-class recipe and exits non-zero. Resolve by hand
in the live `data/` checkout, then re-run `sync-data.sh`. File classes:
`log.md` keep-both/sort-by-date · `wiki/**` union `sources:` · `handoffs/**`
keep newer `updated:` · `raw/**` conflict = immutability violation, investigate.
