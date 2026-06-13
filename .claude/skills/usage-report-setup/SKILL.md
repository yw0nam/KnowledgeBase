---
name: usage-report-setup
description: Use when choosing OpenCode, Hermes, or Claude Code usage report modes — creating or auditing source-specific daily report cron jobs, configuring report output paths, handling missing telemetry sources, or wiring usage reports before daily memory builds.
---

# Usage Report Setup

Use this skill as the runtime contract for source-specific usage report setup. Do not look for a workflow doc during execution; this skill is the complete operating surface.

## Policy

Generate separate reports by source. Do not create a combined usage report in this layer; daily memory synthesis may read multiple source reports and write one combined memory summary later.
Reports are written in-process through the `kb.service` layer (lint → DB → Markdown
export). Markdown under `data/wiki/` is generated export, not the source of truth.
Set `DATABASE_URL` (and optionally `KB_DATA_DIR`) before running any non-dry-run
report command. There is no token to set.

| Source | Command | DB Output |
|---|---|---|
| OpenCode | `uv run kb-opencode-daily-report --date YYYY-MM-DD --lint` | CLI writes metrics + summary page in-process via the service layer |
| Hermes | `uv run kb-hermes-daily-report --date YYYY-MM-DD --lint` | CLI writes metrics + summary page in-process via the service layer |
| Claude Code | `uv run kb-claude-code-daily-report --date YYYY-MM-DD --lint` | CLI writes metrics + summary page in-process via the service layer |

Metrics are canonical in the DB, written by the CLI through the service layer; a derived `.metrics.json` is exported under `data/ops/reports/`, not authored by hand.

## Setup Workflow

1. Inspect which report commands exist:
   ```bash
   uv run kb-opencode-daily-report --help
   uv run kb-hermes-daily-report --help
   uv run kb-claude-code-daily-report --help
   ```
2. Ask the user which modes to enable if not already specified:
   - none
   - OpenCode only
   - Hermes only
   - Claude Code only
   - multiple separate reports
3. Verify matching wrapper scripts under `scripts/cron/`.
4. Ensure usage report jobs run before daily memory build.
5. Propose crontab entries. Do not install them unless the user explicitly approves installation.
6. Run a manual dry run only for selected sources.
7. Verify service-layer write success, generated markdown export, and metrics JSON output.

## Cron Schedule

Recommended KST ordering:

```cron
10 3 * * * <repo-root>/scripts/cron/kb-opencode-daily-report.sh
15 3 * * * <repo-root>/scripts/cron/kb-hermes-daily-report.sh
20 3 * * * <repo-root>/scripts/cron/kb-claude-code-daily-report.sh
30 3 * * * <repo-root>/scripts/cron/kb-memory-daily.sh
```

Enable only selected sources.

## Wrapper Contract

Each wrapper must:

1. Resolve `KB_ROOT` from the script location.
2. Create `.cron/locks`.
3. Use a source-specific `flock` lock.
4. Compute target date in KST as yesterday.
5. Compute `LOG_FILE="$KB_ROOT/data/raw/ops/cron/$(TZ=Asia/Seoul date -d "$TARGET_DATE" +%Y/%m)/${TARGET_DATE}_kb-<source>-daily-report.log"` and `mkdir -p` its parent.
6. Run the source-specific report command with `--lint`, redirecting stdout/stderr to `$LOG_FILE`.
7. Submit the completed wrapper log through `uv run kb-submit-cron-run`.
8. Exit non-zero if the report command or DB log submission fails.

Example command inside a wrapper:

```bash
uv run kb-opencode-daily-report --date "$TARGET_DATE" --lint
```

## Missing Source Handling

If a selected source is not installed or has no database/telemetry:

- do not fail unrelated source report jobs
- do not generate a misleading empty success report unless the user requested empty-day reports
- write a clear wrapper log entry
- if an agent is involved, write a handoff or operation log through the service layer

## Output Rules

Daily usage report markdown must:

- use `type: summary`
- use `subtype: daily`
- set `date`, `created`, and `updated`
- use `sources: []` for local DB/telemetry inputs
- avoid dollar signs; write `N USD`
- be accepted by the service-layer write (the same path the report CLI uses); Markdown is exported after the DB write

## Validation

For each enabled source:

```bash
uv run kb-<source>-daily-report --date YYYY-MM-DD --lint
# DB is canonical and write-only (no read endpoints). The command prints
# `export.status: success` on a good write; confirm the derived exports landed:
ls data/wiki/summaries/YYYY/MM/*-<source>-usage.md
ls data/ops/reports/YYYY/MM/*-usage.metrics.json
```

Do not commit `data/`; it is generated export.

## Red Flags

- About to create a combined usage report command in this layer.
- About to treat a missing optional source as failure for all reports.
- About to run daily memory before selected usage reports.
- About to install crontab entries without explicit user approval.
