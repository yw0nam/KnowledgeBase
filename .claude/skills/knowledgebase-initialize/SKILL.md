---
name: knowledgebase-initialize
description: Use on a fresh clone, new machine, or new profile to create or repair the local data repository — verifying CLI tooling, choosing usage report mode, proposing cron jobs, and writing initialization handoff/log output.
---

# KnowledgeBase Initialize

Use this skill as the runtime contract for repository setup. Do not load `docs/` during execution; docs are design reference only.

## Rules

- Treat the current directory as the KnowledgeBase root.
- `data/` is a nested private git repository. Never add it to the outer repo. It may have its own private remote — see `docs/data-sync.md`.
- Never modify existing files under `data/raw/`.
- Preserve existing `data/` contents; create only missing directories/files.
- Do not install or edit crontab until the user approves the exact entries.
- Memory cron jobs run lint and leave changes uncommitted for manual review.
- Wiki promotion may commit inside the nested `data/` repo after promoting pages. It does not push from the AI session — push to a private `data/` remote (if configured — see `docs/data-sync.md`) is handled outside the AI session.
- Prefer relative paths from repo root. Do not hard-code machine-specific absolute paths except when showing final crontab examples.

## Required Data Layout

```text
data/
  raw/
    github/
      claude-md/
      issues/
    conversations/
    calendar/
    web/
    manual/
    ops/
      cron/YYYY/MM/
      runs/YYYY/MM/
      decisions/YYYY/MM/
      traces/YYYY/MM/
      ingest_state/
  handoffs/YYYY/MM/
  wiki/
    entities/<subject>/YYYY-MM/
    concepts/
    decisions/
    questions/
    improvements/YYYY-MM/
    checklists/
    summaries/YYYY/MM/
  rejected/
  ops/
    reports/YYYY/MM/
  log.md
```

`data/rejected/` may be empty on a fresh install. It is populated by wiki rejection.

## Phase 1: Inspect

Check:

```bash
test -d data
test -d data/.git
test -f data/log.md
uv --version
uv run kb-lint-wiki --help
uv run kb-lint-handoff --help
uv run kb-wiki-review list --counts
find scripts/cron -maxdepth 1 -type f -name 'kb-*.sh' | sort
```

If a command fails because dependencies are missing, run:

```bash
uv sync
```

If `uv sync` needs network and fails due sandbox/network restrictions, ask for approval to rerun with network access.

## Phase 2: Initialize Data Repo

If `data/` already exists with a `.git/`, skip this phase. Otherwise, **ask the
user whether they already have a private `data/` repository to clone** (e.g.
from a previous machine):

- **Yes** → clone it. Its `origin` becomes the private remote that everything
  else derives from — no repo URL is hardcoded anywhere:

  ```bash
  git clone <private-git-url> data
  ```

  The URL must be a private repo scoped to `data/` only — never the outer repo's
  URL or any public host. The remote is now attached, so **skip Phase 2.5** and
  continue at Phase 2.6.

- **No** (fresh start) → create an empty nested repo:

  ```bash
  mkdir -p data
  git -C data init
  ```

  Attach a private remote later via Phase 2.5 when you want to sync.

Create missing required directories with `.gitkeep` only when an empty directory must be tracked by the nested repo.

Initialize `data/log.md` if missing:

```markdown
# KnowledgeBase Log

Append-only operation record.
```

Do not create raw source files during initialization.

## Phase 2.5: Configure Private Data Remote (optional)

Skip this phase if Phase 2 cloned an existing private repo (the remote is already attached).

If `data/` was freshly initialized and the user wants to sync it across machines, ask whether to attach a private remote now. If yes:

```bash
bash .claude/skills/data-sync/scripts/setup-data-remote.sh <git-url>
```

- The URL must be a private repository scoped to `data/` only.
- Never point it at the outer repo's URL or any public host.
- See the `data-sync` skill (`docs/data-sync.md`) for the full workflow and conflict recovery.

Skip this phase on machines that won't sync. The script is idempotent and can be run later.

## Phase 2.6: Install Data CI Workflow

Run while `data/` is **on `master`** (before the work-branch checkout):

```bash
bash .claude/skills/data-sync/scripts/setup-data-ci.sh <pin>
```

`<pin>` is the tag or SHA of the outer repo that includes the `KB_DATA_DIR` change (used to pin the CI workflow to a known-good version). See the `data-sync` skill as the runtime contract.
GitHub Free private repos cannot enforce protected branches. After setup, merge
data PRs only through `data-sync/scripts/merge-data-pr.sh`, which verifies the
remote `lint` result and pins the reviewed head SHA.

## Phase 2.7: Check Out Work Branch

Migrate `data/` from `master` onto a work branch:

```bash
bash .claude/skills/data-sync/scripts/setup-data-workbranch.sh
```

After this, `data/` will be on `sync/<machine>-<date>-<rand>`. AI/cron sessions commit only to work branches. See the `data-sync` skill as the runtime contract.

**If this machine's `data/` already has commits ahead of `origin/master`** (local
`master` or a feature branch), do **not** run Phases 2.6–2.7 as-is: installing CI
while `master` is ahead pushes those commits straight to `master`. Follow the
migration recipe in `docs/data-sync.md` Appendix E (back up → reset master →
CI → cherry-pick → work branch) instead.

## Phase 3: Verify Tooling

Run from repo root:

```bash
uv run kb-wiki-index
uv run kb-lint-wiki --check-immutability
uv run kb-lint-handoff
uv run kb-wiki-review list --counts
```

Fresh empty data may produce no queue items. Structural errors are blockers; existing user-data lint errors must be reported rather than auto-rewritten.

## Phase 3.5: Expose Global Skills

Some KB skills are used **outside this repo** (e.g. `handoff-document`, when
writing handoffs from another project). Install them into the user's global
Claude skills dir as symlinks so the repo stays the single source of truth — a
manual copy drifts:

```bash
bash .claude/skills/knowledgebase-initialize/scripts/install-global-skills.sh
```

- Idempotent. Symlinks `~/.claude/skills/<name>` → this repo's `.claude/skills/<name>`.
- A pre-existing real directory (a drifted manual copy) is backed up to
  `~/.claude/skills.pre-symlink-backups/<name>` (outside the scanned skills dir,
  so it is not loaded as a duplicate skill), never deleted.
- Set `CLAUDE_SKILLS_DIR` to override the destination. Edit the `GLOBAL_SKILLS`
  array in the script to expose more skills (currently: `handoff-document`).

## Phase 4: Usage Report Mode

Use the `usage-report-setup` skill if the user asks for detailed setup. For initialization, ask which source-specific reports to enable:

| Mode | Cron wrapper |
|---|---|
| none | no usage report job |
| OpenCode | `scripts/cron/kb-opencode-daily-report.sh` |
| Hermes | `scripts/cron/kb-hermes-daily-report.sh` |
| Claude Code | `scripts/cron/kb-claude-code-daily-report.sh` |
| multiple separate | selected wrappers only |

Default recommendation: enable only sources the user actually runs. Do not create combined usage reports.

## Phase 5: Propose Cron Jobs

KnowledgeBase owns the expected job contract and portable wrapper scripts under `scripts/cron/`; it does not require a specific scheduler backend.

Scheduler backend guidance:

- **Tested scheduler**: Hermes cron, using scheduler-local dispatcher scripts that call the repo wrappers.
- **Compatible but not yet tested here**: OpenClaw cron, native Unix crontab, systemd timers, or any equivalent scheduler that can run the wrapper scripts on the documented schedule.
- Actual job registration state belongs to the chosen scheduler backend. Run evidence belongs in `data/raw/ops/cron/{YYYY}/{MM}/` (per-run log files), `data/handoffs/`, `data/log.md`, and cron wrap-up summaries.

Show the exact list before making cron changes:

```text
KnowledgeBase jobs:
- daily memory build:        03:30 every day
- wiki promote:              04:00 every day
- weekly memory build:       04:15 every Monday
- monthly memory maintenance:04:45 on day 1 of each month
- wiki TTL sweep:            00:30 every day
- cron wrap-up:              05:00 every day

Optional usage report jobs:
- OpenCode daily usage:      03:10 every day
- Hermes daily usage:        03:15 every day
- Claude Code daily usage:   03:20 every day

Optional global digest job:
- morning Slack digest:      09:00 every day (optional, recommended)
```

If the user wants the optional global digest, read `reference/optional-global-digest.md` and show the setup separately from the required KB cron jobs.

Wrapper prompt policy:

- Memory wrappers import `.claude/skills/memory-report/SKILL.md`.
- Wiki promotion wrapper imports `.claude/skills/wiki-approval/SKILL.md`.
- Cron wrap-up wrapper imports `.claude/skills/cron-wrapup/SKILL.md` and writes a Slack-digest-stable `wiki/summaries/.../{date}-cron-wrapup.md` plus run handoff.
- Usage setup/import prompts use `.claude/skills/usage-report-setup/SKILL.md`.
- TTL sweep may run `uv run kb-wiki-review ttl-sweep --days 7` directly.

Only after approval:

1. Create or update wrapper scripts under `scripts/cron/`.
2. Make wrappers executable.
3. Each wrapper writes its run log to `data/raw/ops/cron/{YYYY}/{MM}/{TARGET}_kb-<job>.log` (where YYYY/MM derives from TARGET_DATE). The `kb-cron-wrapup` wrapper writes to `.cron/logs/cron-wrapup.log` during the session, then commits it to `data/raw/ops/cron/` in a follow-up commit after the session exits.
4. Keep locks in `.cron/locks/`.
5. Show scheduler entries for the selected backend, or install/register them only if the user explicitly asks.

## Phase 6: Initialization Handoff

Write:

```text
data/handoffs/YYYY/MM/kb-initialize/kb-initialize_<role>_handoff_01.md
```

Use role `opencode`, `claude_code`, `hermes`, or `user`. If the role contains an underscore, keep the `kb-initialize_` subject prefix.

Frontmatter:

```yaml
---
handoff_id: "kb-initialize:kb-initialize:<role>:01"
task_slug: "kb-initialize"
subject: "kb-initialize"
role: <role>
handoff_seq: 1
created: "YYYY-MM-DD"
updated: "YYYY-MM-DD"
status: ready
security:
  contains_secrets: false
  redaction_status: unchecked
promotion: null
---
```

Include:

```markdown
## 1. Assignment
## 2. Context received
## 3. Work performed
## 4. Tool trace
## 5. Findings / decisions
## 6. Outputs
## 7. Verification
## 8. Risks / uncertainties
## 9. Next handoff instructions
## 10. Promotion candidates
```

Run:

```bash
uv run kb-lint-handoff
```

## Phase 7: Log

Append to `data/log.md`:

```markdown

## YYYY-MM-DD (knowledgebase initialize)

- **data repo**: exists / created
- **directories**: created <list> / already present
- **tooling**: <lint command results>
- **global skills**: symlinked <list> / skipped
- **usage reports**: <selected modes>
- **cron**: proposed / approved / skipped
- **handoff**: handoffs/YYYY/MM/kb-initialize/<file>.md
```

## Done Criteria

- `data/` exists and has `.git/`.
- Required directories and `data/log.md` exist.
- CLI smoke tests ran or blockers are documented.
- Global skills are symlinked into `~/.claude/skills/` or explicitly skipped.
- Usage report mode is selected or explicitly skipped.
- Cron entries are proposed or explicitly skipped.
- Initialization handoff exists and passes lint.
- No existing `data/raw/` file was modified.

## Red Flags

- About to write private data into the outer repo.
- About to install crontab without explicit approval.
- About to add auto-commit to daily/weekly/monthly memory wrappers.
- About to rewrite existing user data to satisfy lint without instruction.
