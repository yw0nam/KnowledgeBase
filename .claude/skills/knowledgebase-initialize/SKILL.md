---
name: knowledgebase-initialize
description: Initialize this KnowledgeBase for a new user or machine. Sets up the local data repository, creates the required raw/wiki/handoff folders, verifies lint tooling, and proposes cron jobs for user approval before enabling them.
license: MIT
---

# KnowledgeBase Initialize

Use this skill when a user wants to start using this KnowledgeBase on a fresh clone, new machine, or new profile.

## Rules

- Treat the current repository as the KnowledgeBase root.
- Never write private operational data into the outer repo except `.cron/` wrappers if the user approves cron setup.
- Never edit existing files under `data/raw/`.
- New wiki pages of types `entity`, `concept`, `decision`, `improvement`, `checklist`, `question` start as `review_status: not_processed` (template default) and graduate to `pending_for_approve` → `approved` via `kb-wiki-review`. Non-approved pages are intentionally excluded from `INDEX.md` and orphan/sync warnings.
- The `## User Feedback` heading inside a wiki page body is reserved exclusively for the `kb-wiki-review` CLI. Never use that exact heading as a regular content section.
- Do not create, modify, or install cron jobs until the user approves the exact job list.
- Memory cron jobs (daily/weekly/monthly) run lint but do **not** commit. Changes are left uncommitted for manual review. Do not add `git commit` or `git push` to memory cron wrappers.
- Prefer relative paths and repo-root-derived paths. Do not hard-code machine-specific absolute paths.
- If `data/` already exists, preserve it and only create missing directories/files.

## Read First

Read these documents before changing files:

1. `CLAUDE.md`
2. `docs/README.md`
3. `docs/architecture.md`
4. `docs/workflows/pipeline.md`
5. `docs/workflows/periodic-memory-workflow.md`
6. `docs/workflows/cron-jobs.md`
7. `docs/workflows/usage-reports.md`
8. `docs/reference/frontmatter.md`
9. `docs/reference/wiki-categories.md`
10. `docs/workflows/handoff-system.md`
11. `docs/workflows/wiki-approval-workflow.md`

## Phase 1: Inspect

Check:

- whether `data/` exists
- whether `data/.git/` exists
- whether `data/rejected/` exists (created on first reject; absence is normal on a fresh init)
- whether `uv sync` has been run
- whether `kb-lint-wiki`, `kb-lint-handoff`, and `kb-wiki-review` work through `uv run`
- whether `.cron/` or `scripts/cron/` already exists
- whether the user wants usage reports for OpenCode, Hermes, both, or neither

Do not assume the user has Hermes or OpenCode installed.

## Phase 2: Initialize Data Repository

If `data/` is missing, create it as a nested local-only git repository.

Required directory structure:

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
  handoffs/
  wiki/
    entities/
    concepts/
    decisions/
    questions/
    improvements/
    checklists/
    summaries/
      YYYY/
        MM/
  rejected/                  # populated lazily by `kb-wiki-review reject`; mirrors wiki/ paths
  ops/
    reports/
      YYYY/
        MM/
  log.md
```

Create placeholder `.gitkeep` files only when needed to keep empty directories tracked in the nested `data/` repo. Do not add `data/` to the outer repo.

Initialize `data/log.md` if missing:

```markdown
# KnowledgeBase Log

Append-only operation record.
```

If `data/.git/` is missing, run `git init` inside `data/`. Do not push `data/` anywhere.

## Phase 3: Verify Tooling

Run from the KnowledgeBase root:

```bash
uv sync
uv run kb-lint-wiki
uv run kb-lint-handoff
uv run kb-wiki-review list --counts   # smoke test review CLI (0/0/0 on a fresh init)
```

If lint fails because the wiki is empty, record the result and continue only if there are no structural errors that block initialization. If lint fails due to existing user data, do not rewrite data automatically; report the errors and create a handoff if appropriate.

## Phase 4: Usage Report Mode

Ask the user which usage report modes they want before creating cron wrappers:

| Mode | Output | Use When |
|---|---|---|
| OpenCode only | `data/wiki/summaries/YYYY/MM/YYYY-MM-DD-opencode-usage.md` | User only runs OpenCode |
| Hermes only | `data/wiki/summaries/YYYY/MM/YYYY-MM-DD-hermes-usage.md` | User only runs Hermes |
| Claude Code only | `data/wiki/summaries/YYYY/MM/YYYY-MM-DD-claude-code-usage.md` | User only runs Claude Code |
| Multiple separate reports | one markdown per selected source | User wants independent reports per agent system |
| None | no usage report cron | User only wants wiki memory workflows |

Recommendation: prefer separate source-specific reports by default. Combined daily interpretation belongs to the daily memory workflow, not the usage report cron layer.

## Phase 5: Propose Cron Jobs

Present a concise approval list before making cron changes.

Default proposal:

```text
KnowledgeBase memory jobs:
- daily memory build:   03:30 every day
- wiki promote:         04:00 every day (promote not_processed → pending_for_approve, then commit)
- weekly memory build:  04:15 every Monday
- monthly memory maint: 04:45 on day 1 of each month
- wiki TTL sweep:       00:30 every day (auto-reject not_processed pages older than 7d)

Optional usage report jobs:
- OpenCode daily usage report:    03:10 every day
- Hermes daily usage report:      03:15 every day
- Claude Code daily usage report: 03:20 every day
```

Bind usage report jobs to these commands:

```text
OpenCode: uv run kb-opencode-daily-report --date <YYYY-MM-DD> --lint
Hermes: uv run kb-hermes-daily-report --date <YYYY-MM-DD> --lint
Claude Code: uv run kb-claude-code-daily-report --date <YYYY-MM-DD> --lint
Wiki TTL sweep: uv run kb-wiki-review ttl-sweep --days 7   (wrapper: scripts/cron/kb-wiki-ttl-sweep.sh)
```

Ask one short question:

```text
Which cron jobs should I create? I will not modify crontab until you approve the list.
```

Only after approval:

1. Create wrapper scripts under `scripts/cron/`.
2. Make wrappers executable.
3. Keep wrapper logs under `.cron/logs/`.
4. Keep wrapper locks under `.cron/locks/`.
5. Show the exact crontab entries for the user to install, or install them only if the user explicitly asks.

## Phase 6: Handoff and Log

After initialization, write a handoff:

```text
data/handoffs/YYYY/MM/kb-initialize/system_opencode_handoff_01.md
```

Record:

- data repo status
- directories created
- lint results
- cron jobs proposed
- cron jobs approved or skipped
- remaining setup tasks

Append `data/log.md` with the same operation summary.

## Done Criteria

Initialization is complete when:

- `data/` exists and is a nested git repo
- required directories exist
- `data/log.md` exists
- lint commands have been run or blockers are documented
- cron jobs were either explicitly skipped or approved/proposed
- initialization handoff exists
- no existing `data/raw/` file was modified

## Notes For Implementers

Use `apply_patch` for repository file edits. Use shell commands only for directory creation, git init, chmod, lint, and crontab inspection/installation. Do not commit unless the user explicitly asks.
