# Cron Jobs

Updated: 2026-05-18

## 1. Synopsis

- **Purpose**: Schedule KnowledgeBase periodic memory workflows so fresh-session agents can run daily, weekly, and monthly jobs safely.
- **I/O**: system cron or systemd timer -> locked wrapper command -> agent run -> `data/wiki/`, `data/handoffs/`, `data/log.md`, nested `data/` commit.

## 2. Core Logic

### Job Design

Use a three-layer cron design:

```text
cron/systemd timer
  -> lock + environment wrapper
  -> fresh-session agent prompt
  -> docs/workflows/periodic-memory-workflow.md
```

Do not put the full memory workflow inside crontab. Crontab should only schedule a small wrapper. The wrapper owns path setup, locking, logs, and the agent invocation.

### Required Guarantees

Every cron job must guarantee:

| Requirement | Rule |
|---|---|
| Working directory | Always run from the repository root (`$KB_ROOT`) |
| Fresh context | Agent must read `docs/workflows/periodic-memory-workflow.md` |
| No overlap | Use `flock` per job type |
| Raw safety | Never edit existing `data/raw/` files |
| State handoff | Write/update `data/handoffs/` every run |
| Audit trail | Append `data/log.md` every run |
| Validation | Run required lint commands before commit |
| Commit boundary | Commit only nested `data/` repo, never outer repo |
| Failure record | Write failure handoff and log entry before exit |

### Recommended Schedule

Use KST-oriented windows and avoid running jobs at the exact same minute.

| Job | Schedule | Target Period | Purpose |
|---|---|---|---|
| Daily memory build | `30 3 * * *` | yesterday | Capture and triage new raw data |
| Weekly memory build | `15 4 * * 1` | previous ISO week | Synthesize patterns and promotions |
| Monthly memory maintenance | `45 4 1 * *` | previous month | Consolidate, cleanup, and close loops |
| Wiki TTL sweep | `30 0 * * *` | `not_processed` > 7d | Auto-reject stale draft pages |

Daily should run first. Weekly and monthly should run later so they can consume completed daily summaries.

Usage report jobs are optional and source-specific. See `docs/workflows/usage-reports.md` before enabling OpenCode, Hermes, or Claude Code usage report jobs.

### Lock Files

Use separate lock files:

```text
.cron/locks/daily.lock
.cron/locks/weekly.lock
.cron/locks/monthly.lock
.cron/locks/wiki-ttl-sweep.lock
```

If a lock is held, skip the run and write a wrapper log line. Do not start overlapping agents against the same `data/` repo.

### Log Files

Wrapper logs should stay outside `data/` because they are process logs, not curated memory:

```text
.cron/logs/daily.log
.cron/logs/weekly.log
.cron/logs/monthly.log
```

The agent must still append semantic operation results to `data/log.md`.

### Wrapper Contract

Each wrapper should:

1. Set strict shell options.
2. Resolve `KB_ROOT` from the wrapper script location.
3. Create `.cron/logs/` and `.cron/locks/` if missing.
4. Acquire the correct `flock` lock.
5. Run the agent from `KB_ROOT`.
6. Pass one explicit period argument: daily date, weekly ISO week, or monthly month.
7. Capture stdout/stderr to wrapper log.
8. Exit non-zero if the agent exits non-zero.

The wrapper should not edit wiki files itself. Wiki edits belong to the agent following `docs/workflows/periodic-memory-workflow.md`.

## 3. Usage

### Crontab Entries

Use wrapper scripts instead of inline prompts:

```cron
SHELL=/bin/bash
PATH=/usr/local/bin:/usr/bin:/bin:$HOME/.local/bin

30 3 * * * <repo-root>/scripts/cron/kb-memory-daily.sh
15 4 * * 1 <repo-root>/scripts/cron/kb-memory-weekly.sh
45 4 1 * * <repo-root>/scripts/cron/kb-memory-monthly.sh
30 0 * * * <repo-root>/scripts/cron/kb-wiki-ttl-sweep.sh
```

Optional usage report jobs should be added only after the user selects a mode:

```cron
10 3 * * * <repo-root>/scripts/cron/kb-opencode-daily-report.sh
15 3 * * * <repo-root>/scripts/cron/kb-hermes-daily-report.sh
20 3 * * * <repo-root>/scripts/cron/kb-claude-code-daily-report.sh
```

### Daily Wrapper Shape

```bash
#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KB_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
LOG_DIR="$KB_ROOT/.cron/logs"
LOCK_DIR="$KB_ROOT/.cron/locks"
TARGET_DATE="$(TZ=Asia/Seoul date -d 'yesterday' +%F)"

mkdir -p "$LOG_DIR" "$LOCK_DIR"

flock -n "$LOCK_DIR/daily.lock" bash -lc "
  cd '$KB_ROOT'
  <AGENT_CLI> 'Run the KnowledgeBase daily memory workflow for $TARGET_DATE. Read docs/workflows/periodic-memory-workflow.md first and follow docs/workflows/cron-jobs.md.'
" >> "$LOG_DIR/daily.log" 2>&1
```

### Weekly Wrapper Shape

```bash
#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KB_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
LOG_DIR="$KB_ROOT/.cron/logs"
LOCK_DIR="$KB_ROOT/.cron/locks"
TARGET_WEEK="$(TZ=Asia/Seoul date -d 'last week' +%G-W%V)"

mkdir -p "$LOG_DIR" "$LOCK_DIR"

flock -n "$LOCK_DIR/weekly.lock" bash -lc "
  cd '$KB_ROOT'
  <AGENT_CLI> 'Run the KnowledgeBase weekly memory workflow for $TARGET_WEEK. Read docs/workflows/periodic-memory-workflow.md first and follow docs/workflows/cron-jobs.md.'
" >> "$LOG_DIR/weekly.log" 2>&1
```

### Monthly Wrapper Shape

```bash
#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KB_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
LOG_DIR="$KB_ROOT/.cron/logs"
LOCK_DIR="$KB_ROOT/.cron/locks"
TARGET_MONTH="$(TZ=Asia/Seoul date -d 'last month' +%Y-%m)"

mkdir -p "$LOG_DIR" "$LOCK_DIR"

flock -n "$LOCK_DIR/monthly.lock" bash -lc "
  cd '$KB_ROOT'
  <AGENT_CLI> 'Run the KnowledgeBase monthly memory workflow for $TARGET_MONTH. Read docs/workflows/periodic-memory-workflow.md first and follow docs/workflows/cron-jobs.md.'
" >> "$LOG_DIR/monthly.log" 2>&1
```

Replace `<AGENT_CLI>` with the local non-interactive agent runner. The runner must support a single prompt argument and exit non-zero on failure.

### Agent Prompt Contract

Each scheduled prompt must include:

```text
Run the KnowledgeBase <daily|weekly|monthly> memory workflow for <period>.
Read docs/workflows/periodic-memory-workflow.md first.
Read docs/workflows/cron-jobs.md before executing shell commands.
Use data/handoffs as the operational state board.
Never edit existing data/raw files.
Run required lint commands.
Commit the nested data repo only if lint passes.
If blocked, write a handoff and append data/log.md before exiting.
```

### Failure Policy

If the agent fails:

1. Wrapper log captures process output in `.cron/logs/`.
2. Agent writes a handoff under the relevant workflow path when possible.
3. Agent appends `data/log.md` with failure status when possible.
4. Wrapper exits non-zero.
5. Next run reads the ready handoff and continues or records the blocker.

### Enablement Checklist

- Wrapper scripts exist under `scripts/cron/` and are executable.
- `<AGENT_CLI>` is replaced with a real non-interactive command.
- `uv sync` has been run and lint commands work from `KB_ROOT`.
- `data/` nested repo exists and has a clean baseline.
- `.cron/` is ignored by git if runtime logs and locks should not be committed.
- Manual dry run succeeds for daily before enabling weekly/monthly.

---

## Appendix

### A. Manual Dry Run

```bash
./scripts/cron/kb-memory-daily.sh
```

After the run, verify:

```bash
git status --short
cd data && git status --short
```

### B. PatchNote

- 2026-05-19: Added wiki TTL sweep job (00:30 daily) for auto-rejecting stale `not_processed` pages.
- 2026-05-18: Initial cron job design for periodic memory workflows.
