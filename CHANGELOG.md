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
- Added Phase 1 backend for Improvement → Kanban Dispatch: `GET /api/kanban/boards` (with a 30s in-memory TTL cache, invalidated on successful dispatch) and `POST /api/pages/{stem}/send-to-kanban` for sending a `pending_for_approve` improvement page to a Hermes kanban board. Helpers live in `src/kb_mcp/cli/wiki_review/_kanban.py` (`list_boards`, `create_card`, `archive_card`, `append_dispatch`); the route layer translates them per the spec's error taxonomy and writes the dispatch entry back onto the page's `kanban_dispatches` frontmatter list. Unit and route tests added under `test/test_kanban_helpers.py` and `test/test_kanban_route.py`.

### Changed

- Renamed the Python package `kb_mcp` → `kb`. The original name had no relationship to Model Context Protocol; the new name matches the `kb-` CLI prefix. Updated: all `from kb_mcp...` imports across `src/` and `test/`, the `packages` and 9 `[project.scripts]` entries in `pyproject.toml`, the CI coverage path in `.github/workflows/ci.yml`, the GitHub issue/PR template area selectors, `scripts/lint.sh` module paths, frontend file-path comments, the active Phase 2 design handoff, and `.claude/skills/{cron-wrapup,handoff-document,memory-report}/SKILL.md` references. CLI command names (`kb-lint-wiki`, `kb-web`, etc.) are unaffected. **After pulling, run `uv sync`** to re-register console scripts; otherwise `which kb-web` may still resolve to the previous wheel and fail to import. Historical entries above this one still reference `kb_mcp` deliberately — they describe what shipped at the time.

### Deviations from spec (2026-05-26 improvement-to-kanban design)

- `hermes kanban create` does not accept a `--metadata` flag in the installed Hermes. Per Appendix A item 2, the `{kb_page_stem, kb_source}` pair is now embedded in the card body as a trailing `<!-- kb-meta: {...} -->` HTML comment instead of being passed as a JSON parameter. Future tooling that wants to reverse-lookup KB pages from a card must parse the body, not a metadata field.
- `hermes kanban create --json` returns the new task id under `id`, not `task_id`. `_kanban.create_card` normalizes this to `task_id` at the boundary so the route, response payload, and frontmatter all match the spec's contract.
- `counts` on a board listing is sparse (Hermes omits zero buckets), not the fixed five-key shape sketched in §7.1. The route passes the dict through verbatim; the frontend should default missing keys to zero where it needs them.
- §6.1 noted that `kb-lint-wiki` "MUST be updated" to allow `kanban_dispatches`. The current linter has no allowed-keys allowlist (only `REQUIRED_FM_FIELDS`), so no lint change was needed; a regression test in `test/test_kanban_route.py` locks this in.

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
