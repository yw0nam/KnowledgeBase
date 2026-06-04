---
name: usage-report-setup
description: Use when choosing OpenCode, Hermes, or Claude Code usage report modes — creating or auditing source-specific daily report cron jobs, configuring report output paths, handling missing telemetry sources, or wiring usage reports before daily memory builds.
---

# Usage Report Setup

Use this skill as the runtime contract for source-specific usage report setup. Do not look for a workflow doc during execution; this skill is the complete operating surface.

## Policy

Generate separate reports by source. Do not create a combined usage report in this layer; daily memory synthesis may read multiple source reports and write one combined memory summary later.
Reports are written through the DB API. Markdown under `data/wiki/` is generated
export, not the source of truth. Set `KB_API_TOKEN` before running any non-dry-run
report command. `KB_API_URL` may override the default `http://127.0.0.1:8765`.

| Source | Command | DB Output |
|---|---|---|
| OpenCode | `uv run kb-opencode-daily-report --date YYYY-MM-DD --lint` | Metrics POSTed to DB API; summary page created via `POST /api/pages` |
| Hermes | `uv run kb-hermes-daily-report --date YYYY-MM-DD --lint` | Metrics POSTed to DB API; summary page created via `POST /api/pages` |
| Claude Code | `uv run kb-claude-code-daily-report --date YYYY-MM-DD --lint` | Metrics POSTed to DB API; summary page created via `POST /api/pages` |

Metrics are stored in DB via `POST /api/metrics`. No JSON files on disk.

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
7. Verify DB API write success, generated markdown export, and metrics JSON output.

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
- if an agent is involved, write a handoff or operation log through the DB API

## Output Rules

Daily usage report markdown must:

- use `type: summary`
- use `subtype: daily`
- set `date`, `created`, and `updated`
- use `sources: []` for local DB/telemetry inputs
- avoid dollar signs; write `N USD`
- be accepted by `POST /api/pages`; the API exports Markdown after the DB write

## Validation

For each enabled source:

```bash
uv run kb-<source>-daily-report --date YYYY-MM-DD --lint
# Verify DB metrics and summary page via API:
curl -fsS "$KB_API_URL/api/pages?type=summary&date=YYYY-MM-DD" -H "Authorization: Bearer $KB_API_TOKEN"
curl -fsS "$KB_API_URL/api/metrics?date=YYYY-MM-DD" -H "Authorization: Bearer $KB_API_TOKEN"
uv run kb-submit-cron-run --help
```

Do not commit `data/`; it is generated export.

## Red Flags

- About to create a combined usage report command in this layer.
- About to treat a missing optional source as failure for all reports.
- About to run daily memory before selected usage reports.
- About to install crontab entries without explicit user approval.
