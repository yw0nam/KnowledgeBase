# data/ Private Remote Sync

Updated: 2026-05-28

## 1. Synopsis

- **Purpose**: Sync the nested `data/` git repo across machines via a private git remote, without ever exposing it to the outer repo's remote.
- **I/O**: One private remote URL → `data/` pushable/pullable from any machine that runs `scripts/setup-data-remote.sh`.

## 2. Core Logic

### Why a private git remote

`data/` is already a nested git repo. Cron jobs (`kb-cron-wrapup`, `kb-wiki-promote`) and the `wiki-approval` skill commit to it. Git semantics — atomic commits, history, conflict resolution — match this workflow. File-sync products (Google Drive, Dropbox) race against `.git/` and corrupt it.

The outer repo's `.gitignore` excludes `data/`, so a private remote scoped to `data/` only is the safe sync surface. The outer repo's own remote must never see `data/` content.

### Setup

On each machine:

```bash
bash scripts/setup-data-remote.sh git@github.com:<you>/<private-data-repo>.git
```

The script:

1. Verifies `data/` and `data/.git` exist (otherwise refuses).
2. Refuses if `data/` has uncommitted changes.
3. Refuses if `origin` is already set to a different URL.
4. Runs `git -C data remote add origin <url>` and `git -C data push -u origin <branch>`.

Create the private repo first on GitHub (or any private host). Do **not** reuse the outer repo's URL.

### Daily workflow (manual, current model)

- **Start of day** on machine A: `git -C data pull --rebase`
- **After cron-wrapup commit** (around 05:00 KST): `git -C data push`
- Repeat on machine B.

AI sessions and cron jobs commit locally but **do not push**. Push is a deliberate user action so privacy invariants stay visible.

### Conflict recovery

When `git -C data pull --rebase` fails with conflicts:

1. **Inspect**: `git -C data status` to list conflicted paths.
2. **Resolve by file class:**

   | Path pattern | Resolution |
   |---|---|
   | `data/log.md` | Append-only: keep both sides, sort by date. |
   | `data/wiki/**/*.md` | Manual merge. For `sources:` frontmatter arrays, take the union. |
   | `data/handoffs/**/*.md` | Handoffs are immutable. A conflict means the same handoff was edited on two machines — keep the side with the newer `updated:` field and record the reason in the next handoff. |
   | `data/raw/**` | Raw files are immutable (CLAUDE.md). A conflict here is an invariant violation: same path was created with different content on two machines. Investigate which side is authentic before continuing. Do **not** push until resolved. |

3. **Finish rebase**: `git -C data rebase --continue`.
4. **Lint before pushing**:

   ```bash
   uv run kb-wiki-index
   uv run kb-lint-wiki --check-immutability
   uv run kb-lint-handoff
   ```

5. **Push**: `git -C data push`.

If the conflict is too large to merge by hand, create a per-machine branch (e.g. `machine-a`, `machine-b`), push both, and resolve in a long-form merge on one machine.

### Privacy guardrails

- The outer repo's `.gitignore` already excludes `data/`. Do not unset that.
- Never set the `data/` remote URL to the outer repo's URL or any public host.
- AI sessions (cron-wrapup, wiki-promote, memory-report) commit to `data/` but never push. Push remains a user/setup action.

## 3. Usage

| Need | Command |
|---|---|
| Configure private remote on a new machine | `bash scripts/setup-data-remote.sh <url>` |
| Pull updates before working | `git -C data pull --rebase` |
| Push after cron-wrapup commits | `git -C data push` |
| Inspect current remote | `git -C data remote -v` |
| Change remote URL | `git -C data remote set-url origin <new-url>` |

---

## Appendix

### A. Future: automated sync

A later PR will add:

- A `cron-wrapup` post-commit hook that pushes to the private remote.
- A session-start hook that runs `git -C data pull --rebase` before AI workflows begin.

Until then, push and pull are manual. This is intentional — automatic push hides privacy decisions that should be conscious.

### B. State DB (`data/db/`)

`data/db/` is excluded by `data/.gitignore` and is not synced via git. The current memory workflow keeps markdown frontmatter as the source of truth; `state.db` is derivable per-machine. A future migration to "DB as source of truth" will require a separate sync mechanism (rsync, litestream, etc.).

### C. PatchNote

- 2026-05-28: Initial publication. Establishes private-remote model, conflict recovery guide, and future hook roadmap.
