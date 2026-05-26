# Changelog

## Maintenance Contract

This file records outer repository changes only. Use it for changes to source code, scripts, docs, skills, templates, config, schemas, CLI behavior, cron wrappers, and workflow contracts.

Do not record local data artefacts here. Changes under the nested `data/` repo belong in `data/log.md` and the relevant handoff/wiki pages.

Use `## Unreleased` for work not yet released. Within it, use these headings when relevant:

- `### Added` for new features, scripts, skills, templates, docs, or workflows.
- `### Changed` for behavior, contract, schedule, schema, or documentation changes.
- `### Fixed` for bug fixes and corrected broken behavior.
- `### Removed` for deleted features, scripts, skills, docs, or workflows.

Keep entries concise and user/operator-facing. Avoid tool traces, lint output, handoff paths, and private data details unless they are necessary to understand the change.

## Unreleased

### Added

- Added a README screenshot for the local review console.
- Added the `cron-wrapup` skill and `kb-cron-wrapup.sh` wrapper for nightly KB operational summaries.
- Added optional global digest guidance under `knowledgebase-initialize/reference/optional-global-digest.md`.

### Changed

- Updated `knowledgebase-initialize` to include `cron wrap-up` as a required KB cron proposal and the morning digest as optional but recommended.
- Clarified that KnowledgeBase cron jobs use portable wrappers with Hermes cron as the tested scheduler backend, while OpenClaw cron, native cron, and systemd timers are compatible but untested here.
- Expanded the `cron-wrapup` summary contract with `Insights` and `Action Items` sections so daily wrap-ups surface user-facing KB signals, not only job status.
- Updated the cron-wrapup template and optional digest prompt to consume the expanded summary contract.
- Clarified that `kb-cron-wrapup` commits only nested `data/` repo outputs after successful lint, while the optional global digest remains read-only and report-only.
- Cron wrappers now write per-run logs to `data/raw/ops/cron/{YYYY}/{MM}/{TARGET}_kb-<job>.log` instead of appending to `.cron/logs/<job>.log`. The cron wrap-up reads each target's per-run files directly and stages them with its data commit. The `kb-cron-wrapup` wrapper itself still logs to `.cron/logs/cron-wrapup.log` to avoid staging an in-flight file during its own commit.
- Aligned the root `CLAUDE.md` cron-wrapup skill summary with the current per-run cron evidence path under `data/raw/ops/cron/`.

### Fixed

- Fixed Claude Code daily report tool-call and user-prompt counts being inflated ~250x by overlapping `count_over_time([24h])` sliding windows. `_collect_loki` now uses a new `_query_loki_instant` helper to evaluate the 24h aggregation once at the day boundary instead of summing across query_range step points. Affects `tool_breakdown`, `n_toolcalls`, `error_rate`, and `n_turns`; per-tool error rates were already accurate because numerator and denominator inflated equally.
