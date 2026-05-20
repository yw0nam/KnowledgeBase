---
name: usage-report-setup
description: Self-contained KnowledgeBase usage report setup workflow. Use when choosing OpenCode, Hermes, or Claude Code usage report modes, creating or auditing source-specific daily report cron jobs, configuring report output paths, handling missing telemetry sources, or wiring usage reports before daily memory builds. Also covers the legacy workflow name usage_report_setup.
---

# Usage Report Setup

Use this skill as the runtime contract for source-specific usage report setup. Do not look for a workflow doc during execution; this skill is the complete operating surface.

## Policy

Generate separate reports by source. Do not create a combined usage report in this layer; daily memory synthesis may read multiple source reports and write one combined memory summary later.

| Source | Command | Markdown output |
|---|---|---|
| OpenCode | `uv run kb-opencode-daily-report --date YYYY-MM-DD --lint` | `data/wiki/summaries/YYYY/MM/YYYY-MM-DD-opencode-usage.md` |
| Hermes | `uv run kb-hermes-daily-report --date YYYY-MM-DD --lint` | `data/wiki/summaries/YYYY/MM/YYYY-MM-DD-hermes-usage.md` |
| Claude Code | `uv run kb-claude-code-daily-report --date YYYY-MM-DD --lint` | `data/wiki/summaries/YYYY/MM/YYYY-MM-DD-claude-code-usage.md` |

Metrics JSON belongs under:

```text
data/ops/reports/YYYY/MM/
```

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
7. Verify markdown output, metrics JSON output, and lint result.

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
2. Create `.cron/logs` and `.cron/locks`.
3. Use a source-specific `flock` lock.
4. Compute target date in KST as yesterday.
5. Run the source-specific report command with `--lint`.
6. Write process logs to `.cron/logs/<source>-daily-report.log`.
7. Exit non-zero if the report command fails.

Example command inside a wrapper:

```bash
uv run kb-opencode-daily-report --date "$TARGET_DATE" --lint
```

## Missing Source Handling

If a selected source is not installed or has no database/telemetry:

- do not fail unrelated source report jobs
- do not generate a misleading empty success report unless the user requested empty-day reports
- write a clear wrapper log entry
- if an agent is involved, write a handoff or append `data/log.md` with `skipped`

## Output Rules

Daily usage report markdown must:

- use `type: summary`
- use `subtype: daily`
- set `date`, `created`, and `updated`
- use `sources: []` for local DB/telemetry inputs
- avoid dollar signs; write `N USD`
- pass `uv run kb-lint-wiki`

## Validation

For each enabled source:

```bash
uv run kb-<source>-daily-report --date YYYY-MM-DD --lint
test -f data/wiki/summaries/YYYY/MM/YYYY-MM-DD-<source>-usage.md
uv run kb-lint-wiki
```

Then inspect:

```bash
git -C data status --short
```

Do not commit unless the user explicitly asks.

## Red Flags

- About to create a combined usage report command in this layer.
- About to treat a missing optional source as failure for all reports.
- About to run daily memory before selected usage reports.
- About to install crontab entries without explicit user approval.
