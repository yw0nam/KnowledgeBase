---
name: knowledgebase-initialize
description: Use on a fresh clone, new machine, or new profile to set up KnowledgeBase — choosing deployment mode (local compose bring-up vs connecting to a remote DB/daemon over an SSH tunnel), verifying CLI tooling, registering kb-mcp in agent runtimes, choosing usage report mode, proposing cron jobs, and writing initialization handoff/log output.
---

# KnowledgeBase Initialize

> **DB-Canonical Override**: The KnowledgeBase is DB-backed. `data/` is a generated Markdown export — do NOT create a nested `data/.git` repo or set up any Git sync for it. The end state is the same in both deployment modes: the `kb-mcp` daemon answers on `:8765` and Postgres is reachable. **Phase 0 decides how you get there** — either bring up the Postgres `db` service and the `kb-mcp` daemon locally via compose (and run migrations), or connect this machine as a client to an already-running **remote** stack (no compose, no migrations). Ask before doing either.

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

## Phase 0: Choose Deployment Mode (ask FIRST)

**Before any DB bring-up, ask where the Postgres DB and `kb-mcp` daemon live.** Do
this before Phase 2 — do not run `docker compose up` on the assumption it is local.

| Mode | Meaning | Phase 2 path |
|---|---|---|
| **Local bring-up** | Stand up `db` + `kb-mcp` on this machine via compose; this machine owns the stack. | Phase 2A |
| **Remote connect** | DB + daemon already run on another host; this machine is a client (often over an SSH tunnel). | Phase 2B |

If the user is unsure, probe first: is anything already listening on `:8765` /
`:15432` locally, or does an SSH host already serve them? Then confirm the choice.

The mode changes three things downstream: Phase 2 (bring up vs connect+tunnel),
Phase 5 cron (a remote client usually **skips** cron — the remote host already runs
the nightly pipeline; registering it here causes duplicate runs), and which
`<KB_MCP_URL>` the runtimes register against.

## Phase 1: Inspect

Check (the DB read here only succeeds once Phase 2 has brought up / connected the
stack — on a cold start it is expected to fail, that is fine):

```bash
test -d data
test -f data/log.md
uv --version
uv run kb-lint --help
uv run kb-db-ttl-sweep --help
find scripts/cron -maxdepth 1 -type f -name 'kb-*.sh' | sort
```

Mode-specific checks:

- **Local bring-up** — confirm Docker is available: `docker info` (if the daemon is
  off, start Docker Desktop / `dockerd` and wait, or ask the user to).
- **Remote connect** — confirm the SSH host resolves and the remote services answer
  (see `reference/remote-connection.md`); do **not** start Docker locally.

`psql` may be absent on a client machine. That is not a blocker — reads can go
through psycopg (the same path `kb.service` uses); see `reference/remote-connection.md`.

If a command fails because dependencies are missing, run:

```bash
uv sync
```

If `uv sync` needs network and fails due sandbox/network restrictions, ask for approval to rerun with network access.

## Phase 2: Bring Up or Connect to the Database

Postgres is the sole source of truth and the `kb-mcp` daemon is the write surface.
Copy `.env.example` → `.env` first in both modes, then follow **2A** or **2B** per
the Phase 0 choice.

```bash
cp -n .env.example .env
set -a; . ./.env; set +a
```

### Phase 2A: Local bring-up

Bring up both compose services:

```bash
docker compose up -d --build        # starts db + the kb-mcp daemon (:8765)
```

The `kb-mcp` daemon runs `alembic upgrade head` on startup, so the schema is
applied automatically. To apply migrations host-side without the daemon, run
`uv run alembic upgrade head`. Confirm the daemon is up:

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8765/mcp   # expect 406 (server alive)
```

### Phase 2B: Remote connect

The DB + daemon already run elsewhere — **do not** `docker compose up` and **do not**
run migrations (the remote stack is canonical and already migrated). Point `.env`'s
`DATABASE_URL` at the remote (often `localhost:<port>` when tunnelled), set the
remote `<KB_MCP_URL>`, and — if the remote is only reachable over SSH — bring up a
**persistent auto-tunnel** (two forwarded ports: kb-mcp `8765` + Postgres). Full
recipe (one-shot tunnel, launchd auto-tunnel template, verification) is in
`reference/remote-connection.md`. A populated remote (non-zero `pages`) confirms you
are a client of a live KB; skip schema/data init.

---

`data/` remains the Markdown export tree (`KB_DATA_DIR`), not the canonical store, in
both modes.

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
# Postgres read smoke test — psql if present, else psycopg (the kb.service path):
psql "${DATABASE_URL/+psycopg/}" -tAc "SELECT count(*) FROM pages;" 2>/dev/null \
 || uv run python -c "import os,psycopg; c=psycopg.connect(os.environ['DATABASE_URL'].replace('+psycopg',''),connect_timeout=8); cur=c.cursor(); cur.execute('select count(*) from pages'); print('pages:',cur.fetchone()[0])"
uv run kb-lint --help
```

Writes go through the kb-mcp tools / the `kb.service` layer; reads go through
`psql`, the psycopg fallback above, or the read-only `query_sql` tool. Verify the
daemon is reachable and the DB answers:

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8765/mcp   # expect 406
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

> **Remote-client default: skip cron here.** If Phase 0 chose **Remote connect** and
> the remote host already runs the nightly pipeline (check `cron_runs` — a populated
> table means it does), registering the same jobs on this machine causes **duplicate
> runs**. Default to *not* registering cron locally; treat this machine as an
> interactive client. Only register here if the user explicitly wants this machine to
> own (a subset of) the schedule. For a fresh **Local bring-up**, propose the full
> list below as normal.

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

### Register kb-mcp in agent runtimes (ask first)

LLM/agent runtimes reach the write surface by connecting to the `kb-mcp` daemon over http.

`<KB_MCP_URL>` is already decided by Phase 0/2: for **Local bring-up** it is
`http://127.0.0.1:8765/mcp`; for **Remote connect** it is the remote URL (or
`http://127.0.0.1:8765/mcp` when reached through the Phase 2B tunnel). Then **ask
which runtimes to register** — one at a time ("Register kb-mcp in opencode? in Claude
Code? in Hermes?") and register only on an explicit yes.

Recipes (use the confirmed `<KB_MCP_URL>`):

- **opencode** — add under `mcp` in `~/.config/opencode/opencode.json`:
  ```json
  "kb-mcp": { "type": "remote", "url": "<KB_MCP_URL>", "enabled": true }
  ```
- **Claude Code** — `claude mcp add --transport http --scope user kb-mcp <KB_MCP_URL>`.
  Note: a server added mid-session is **not** loaded into the *current* Claude Code
  session — restart to use its tools in-session (see Phase 6).
- **Hermes** — `hermes mcp add kb-mcp --url <KB_MCP_URL>`. It is **interactive**:
  answer `n` to "Does this server require authentication?" (kb-mcp has no auth), then
  `Y` to "Enable all N tools?". Drive it with a pty if running non-interactively.
- **Other runtimes** — ask the user where their MCP config lives; add an http entry pointing at `<KB_MCP_URL>`.

Deterministic jobs (`kb-db-ttl-sweep`, daily reports, ingest) need no registration — they call `kb.service` in-process. The daemon has no auth: if it must be reachable from other hosts, publish it on the appropriate interface (compose default `0.0.0.0:8765`); on a single host, host-loopback (`127.0.0.1:8765:8765`) is safer (see #41).

Only after approval:

1. Create or update wrapper scripts under `scripts/cron/`.
2. Make wrappers executable.
3. Each wrapper writes its run log to `data/raw/ops/cron/{YYYY}/{MM}/{TARGET}_kb-<job>.log` (where YYYY/MM derives from TARGET_DATE). The `kb-cron-wrapup` wrapper writes to `.cron/logs/cron-wrapup.log` during the session, then commits it to `data/raw/ops/cron/` in a follow-up commit after the session exits.
4. Keep locks in `.cron/locks/`.
5. Show scheduler entries for the selected backend, or install/register them only if the user explicitly asks.

## Phase 6: Initialization Handoff

Write:

```text
data/handoffs/YYYY/MM/kb-initialize/kb-initialize_<role>_handoff_<NN>.md
```

Use role `opencode`, `claude_code`, `hermes`, or `user`. If the role contains an underscore, keep the `kb-initialize_` subject prefix.

**Pick `<NN>` / `handoff_seq` by checking what already exists** — `handoff_id` is
UNIQUE in the DB, so a second init on the same KB with `:01` fails with a `conflict`.
Query first and use the next sequence:

```bash
uv run python -c "import os,psycopg; c=psycopg.connect(os.environ['DATABASE_URL'].replace('+psycopg',''),autocommit=True); cur=c.cursor(); cur.execute(\"select handoff_id,handoff_seq from handoffs where task_slug='kb-initialize' order by handoff_seq\"); [print(r) for r in cur.fetchall()]"
```

Frontmatter (`<NN>` zero-padded, e.g. `02`):

```yaml
---
handoff_id: "kb-initialize:kb-initialize:<role>:<NN>"
task_slug: "kb-initialize"
subject: "kb-initialize"
role: <role>
handoff_seq: <NN>
created: "YYYY-MM-DD"
updated: "YYYY-MM-DD"
status: ready
security:
  contains_secrets: false
  redaction_status: unchecked
promotion: null
---
```

**`export_path` is relative to `KB_DATA_DIR`** — pass `handoffs/YYYY/MM/...`, **not**
`data/handoffs/...`. Prefixing `data/` doubles the path into `data/data/...` on export.

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

Submit through the kb-mcp `create_handoff` tool — handoff validation runs inside it
(returns `code: lint_failed` on failure).

**If the kb-mcp tools are not available in the current session** (e.g. you registered
kb-mcp in Claude Code mid-session and have not restarted), submit via the in-process
`kb.service` layer instead — it is the exact path the tool wraps (lint → DB → export):

```python
from kb.service.session import session_scope
from kb.service.handoffs import create_handoff
with session_scope() as (session, data_dir):
    create_handoff(session, data_dir, handoff_id=..., task_slug="kb-initialize",
                   role=..., handoff_seq=..., status="ready", frontmatter=fm,
                   body_md=body, export_path="handoffs/YYYY/MM/kb-initialize/<file>.md",
                   subject="kb-initialize", created_at=DATE, updated_at=DATE)
```

(Requires `DATABASE_URL` and `KB_DATA_DIR` set in the env.)

## Phase 7: Log

Write the setup note through the kb-mcp `create_operation_log` tool — or, if the
tools are not loaded in-session, `kb.service.ops.create_operation_log` via
`session_scope()` (same in-process path). The generated export may update `data/log.md`:

```markdown

## YYYY-MM-DD (knowledgebase initialize)

- **mode**: local bring-up / remote connect
- **DB**: created / existing remote (pages=<n>, alembic head <rev>)
- **tunnel**: <none / launchd com.local.kb-tunnel: 8765 + 15432>
- **directories**: created <list> / already present
- **tooling**: <lint command results>
- **global skills**: symlinked <list> / skipped
- **kb-mcp registration**: <runtimes> / skipped
- **usage reports**: <selected modes>
- **cron**: proposed / approved / skipped (remote owns pipeline)
- **handoff**: handoffs/YYYY/MM/kb-initialize/<file>.md
```

## Done Criteria

- Deployment mode was chosen with the user (Phase 0) before any DB bring-up.
- The `kb-mcp` daemon is reachable on `:8765` and Postgres answers — whether via local
  compose (migrations applied) or a remote connection (tunnel up if SSH-only).
- Required directories and `data/log.md` exist.
- CLI smoke tests ran or blockers are documented.
- Global skills are symlinked into `~/.claude/skills/` or explicitly skipped.
- kb-mcp is registered in the agent runtimes the user approved (or explicitly skipped).
- Usage report mode is selected or explicitly skipped.
- Cron entries are proposed, registered, or explicitly skipped (skipped is the default for a remote client whose remote already runs the pipeline).
- Initialization handoff exists (next free `handoff_seq`) and passes lint.
- No existing `data/raw/` file was modified.

## Red Flags

- About to write private data into the outer repo.
- About to `docker compose up` before confirming the deployment mode (Phase 0).
- About to register cron on a remote client whose remote already runs the pipeline (duplicate runs).
- About to install crontab without explicit approval.
- About to add auto-commit to daily/weekly/monthly memory wrappers.
- About to rewrite existing user data to satisfy lint without instruction.
