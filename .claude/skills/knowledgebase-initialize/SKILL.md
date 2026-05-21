---
name: knowledgebase-initialize
description: Use on a fresh clone, new machine, or new profile to create or repair the local data repository — verifying CLI tooling, choosing usage report mode, proposing cron jobs, and writing initialization handoff/log output.
---

# KnowledgeBase Initialize

Use this skill as the runtime contract for repository setup. Do not load `docs/` during execution; docs are design reference only.

## Rules

- Treat the current directory as the KnowledgeBase root.
- `data/` is a nested local-only git repository. Never add it to the outer repo.
- Never modify existing files under `data/raw/`.
- Preserve existing `data/` contents; create only missing directories/files.
- Do not install or edit crontab until the user approves the exact entries.
- Memory cron jobs run lint and leave changes uncommitted for manual review.
- Wiki promotion may commit inside the nested `data/` repo after promoting pages. It never pushes.
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

If `data/` is missing, create it and initialize a nested repo:

```bash
mkdir -p data
git -C data init
```

Create missing required directories with `.gitkeep` only when an empty directory must be tracked by the nested repo.

Initialize `data/log.md` if missing:

```markdown
# KnowledgeBase Log

Append-only operation record.
```

Do not create raw source files during initialization.

## Phase 3: Verify Tooling

Run from repo root:

```bash
uv run kb-wiki-index
uv run kb-lint-wiki --check-immutability
uv run kb-lint-handoff
uv run kb-wiki-review list --counts
```

Fresh empty data may produce no queue items. Structural errors are blockers; existing user-data lint errors must be reported rather than auto-rewritten.

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

Show the exact list before making cron changes:

```text
KnowledgeBase jobs:
- daily memory build:        03:30 every day
- wiki promote:              04:00 every day
- weekly memory build:       04:15 every Monday
- monthly memory maintenance:04:45 on day 1 of each month
- wiki TTL sweep:            00:30 every day

Optional usage report jobs:
- OpenCode daily usage:      03:10 every day
- Hermes daily usage:        03:15 every day
- Claude Code daily usage:   03:20 every day
```

Wrapper prompt policy:

- Memory wrappers import `.claude/skills/memory-report/SKILL.md`.
- Wiki promotion wrapper imports `.claude/skills/wiki-approval/SKILL.md`.
- Usage setup/import prompts use `.claude/skills/usage-report-setup/SKILL.md`.
- TTL sweep may run `uv run kb-wiki-review ttl-sweep --days 7` directly.

Only after approval:

1. Create or update wrapper scripts under `scripts/cron/`.
2. Make wrappers executable.
3. Keep logs in `.cron/logs/`.
4. Keep locks in `.cron/locks/`.
5. Show crontab entries, or install them only if the user explicitly asks.

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
- **usage reports**: <selected modes>
- **cron**: proposed / approved / skipped
- **handoff**: handoffs/YYYY/MM/kb-initialize/<file>.md
```

## Done Criteria

- `data/` exists and has `.git/`.
- Required directories and `data/log.md` exist.
- CLI smoke tests ran or blockers are documented.
- Usage report mode is selected or explicitly skipped.
- Cron entries are proposed or explicitly skipped.
- Initialization handoff exists and passes lint.
- No existing `data/raw/` file was modified.

## Red Flags

- About to write private data into the outer repo.
- About to install crontab without explicit approval.
- About to add auto-commit to daily/weekly/monthly memory wrappers.
- About to rewrite existing user data to satisfy lint without instruction.
