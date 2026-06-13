---
name: knowledgebase-initialize
description: Use on a fresh clone, new machine, or new profile to create or repair the local data repository — verifying CLI tooling, choosing usage report mode, proposing cron jobs, and writing initialization handoff/log output.
---

# KnowledgeBase Initialize

> **DB-Canonical Override**: The KnowledgeBase is DB-backed. `data/` is a generated Markdown export — do NOT create a nested `data/.git` repo or set up any Git sync for it. Bring up the Postgres `db` service (compose) and run migrations, and verify the `kb-mcp` server entrypoint resolves and Postgres is reachable.

Use this skill as the runtime contract for repository setup. Do not load `docs/` during execution; docs are design reference only.

## Rules

- Treat the current directory as the KnowledgeBase root.
- `data/` is a generated export directory. Postgres (reached via `DATABASE_URL`) is the canonical store. Never add `data/` to the outer repo.
- Never modify existing files under `data/raw/`.
- Preserve existing `data/` contents; create only missing directories/files.
- Do not install or edit crontab until the user approves the exact entries.
- Memory cron jobs run lint and leave changes uncommitted for manual review.
- Wiki promotion writes through the kb-mcp tools; it does not commit or push from the AI session.
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
psql "${DATABASE_URL/+psycopg/}" -tAc "SELECT 1" >/dev/null && echo "DB reachable"
test -f data/log.md
uv --version
uv run kb-lint --help
uv run kb-db-ttl-sweep --help
find scripts/cron -maxdepth 1 -type f -name 'kb-*.sh' | sort
```

If a command fails because dependencies are missing, run:

```bash
uv sync
```

If `uv sync` needs network and fails due sandbox/network restrictions, ask for approval to rerun with network access.

## Phase 2: Initialize the Database

Postgres is the sole source of truth. Bring up the compose Postgres and run
migrations (copy `.env.example` → `.env` first so `DATABASE_URL` is set):

```bash
cp -n .env.example .env
docker compose up -d db
set -a; . ./.env; set +a
uv run alembic upgrade head
```

In Docker deployment the `kb-mcp` service also runs `alembic upgrade head` on
startup, so `docker compose up -d` is sufficient. `data/` remains as the
Markdown export tree (`KB_DATA_DIR`), not the canonical store.

Create missing required directories under `data/` (export tree only).

Initialize `data/log.md` if missing:

```markdown
# KnowledgeBase Log

Append-only operation record.
```

Do not create raw source files during initialization.

## Phase 3: Verify Tooling

Run from repo root:

```bash
# Direct Postgres read smoke test (reads go straight to psql):
psql "${DATABASE_URL/+psycopg/}" -tAc "SELECT count(*) FROM pages;"
uv run kb-lint --help
```

Writes go through the kb-mcp tools / the `kb.service` layer; Postgres is the
canonical store. Verify the kb-mcp server entrypoint resolves and the DB is
reachable:

```bash
uv run kb-mcp --help
psql "${DATABASE_URL/+psycopg/}" -tAc "select 1"
```

Fresh empty data may produce zero rows. Structural errors are blockers; existing user-data lint errors must be reported rather than auto-rewritten.

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
  array in the script to expose more skills (currently: `handoff-document` and `wiki-note`).

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
- Actual job registration state belongs to the chosen scheduler backend. Run evidence belongs in DB tables (`cron_runs`, `handoffs`, `operation_logs`, and summary `pages`); `data/raw/ops/cron/{YYYY}/{MM}/`, `data/handoffs/`, `data/log.md`, and wrap-up markdown are generated export/debug copies.

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
- TTL sweep runs `uv run kb-db-ttl-sweep --days 7`, applying status changes in-process through the `kb.service` layer.

LLM cron jobs (memory-*, wiki-promote, cron-wrapup) reach the write surface via kb-mcp tools, so the `kb-mcp` server must be registered in opencode as a local stdio MCP. In `~/.config/opencode/opencode.json` under `mcp`, add an entry with type `local`, command `["uv","run","--directory","<KB_ROOT>","kb-mcp","--transport","stdio"]`, and `environment` carrying `DATABASE_URL` and `KB_DATA_DIR`. Deterministic jobs need no server (they call `kb.service` in-process).

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
# Handoff validation runs inside the kb-mcp create_handoff tool (returns code: lint_failed on failure)
```

## Phase 7: Log

Write the setup note through the kb-mcp `create_operation_log` tool (the generated export may update `data/log.md`):

```markdown

## YYYY-MM-DD (knowledgebase initialize)

- **DB**: exists / created
- **directories**: created <list> / already present
- **tooling**: <lint command results>
- **global skills**: symlinked <list> / skipped
- **usage reports**: <selected modes>
- **cron**: proposed / approved / skipped
- **handoff**: handoffs/YYYY/MM/kb-initialize/<file>.md
```

## Done Criteria

- Postgres `db` service is up (migrations applied) and the `kb-mcp` server entrypoint resolves.
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
