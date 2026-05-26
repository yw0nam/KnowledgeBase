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

- Added Phase 2b Task C: Decisions browser backend endpoints. New `src/kb/db/repos/wiki_edit_repo.py` provides function-style `insert_edits` (one row per change, single commit) and `list_edits` (descending with `since` cursor + unfiltered total). `PATCH /api/pages/{stem}/frontmatter` runs the candidate frontmatter through `kb-lint-wiki` against a hardlink-mirror of the corpus (with regenerated `INDEX.md`), atomically rewrites the file via `os.replace`, and inserts one `wiki_edits` row per changed field. Pipeline order is load-bearing; the recovery contract (file written but DB commit failed → 500 with `file_written: true`; client retry computes empty diff → 200 with `edits: []`) is locked in by tests. `type` changes that would require a cross-directory rename are rejected with 409 before any write. New read endpoints: `GET /api/pages/{stem}/edits` (paged audit history), `GET /api/pages/{stem}/timeline` (UNION of edits and dispatch events), `GET /api/decisions` (filterable page listing with `last_edited_at` and `dispatch_summary` joined from the DB), and `GET /api/enums/categories` (distinct category values; open string, not enforced). CORS now allows `PATCH`. Tests in `test/test_wiki_edit_repo.py` (2) and `test/test_route_decisions.py` (8) cover the repo, all four §9.1 PATCH cases, and the new read contracts.
- Added Phase 2a Task B: DB-backed dispatch ledger. New `src/kb/db/repos/dispatch_repo.py` exposes function-style helpers (`create_dispatch` with Idempotency-Key replay, `update_status` with monotonic `occurred_at` and transition-graph enforcement, `cancel_phase_one`, `cancel_phase_two`, `force_cancel`, `list_dispatches`) and three custom exceptions (`DispatchNotFound`, `TransitionViolation`, `StatusOutOfOrder`). New routes under `/api/dispatches`: paginated listing, Bearer-protected status push (`KB_API_TOKEN`), and a two-state cancel endpoint with `?force=true` escape. `POST /api/pages/{stem}/send-to-kanban` no longer writes the page's frontmatter — it inserts a `dispatches` row and returns `{id, external_task_id, external_board_id, dispatched_at}`. New `kb-migrate-kanban-dispatches` console script backfills existing `kanban_dispatches` frontmatter lists into the DB and removes the frontmatter key (idempotent — UNIQUE blocks dupes). `kb.cli.wiki_review._kanban.append_dispatch` is gone along with its four unit tests and the two Phase 1 rollback route tests. App now wires `app.state.engine` / `app.state.session_factory` via the Task A factories.
- Added Phase 2a Task A foundation for the operational state DB: `sqlalchemy>=2.0` and `alembic>=1.13` dependencies, a `src/kb/db/` module exposing `make_engine`, `make_session_factory`, `get_session`, and a `db_path` helper that resolves `<KB_DATA_DIR>/db/state.db`, plus connection-time PRAGMAs (WAL, foreign_keys=ON, busy_timeout=5000ms, synchronous=NORMAL) wired via a SQLAlchemy `Engine` `connect` listener. Initial Alembic migration creates `dispatches` and `wiki_edits` tables with the spec DDL — CHECK constraints on `status`/`field`/`source`, ISO-8601 KST timestamp shape checks, `json_valid` checks on JSON columns, a partial unique index on `dispatches(idempotency_key)`, status- and stem-keyed lookup indexes, and `BEFORE UPDATE`/`BEFORE DELETE` triggers that abort with `'wiki_edits is append-only'`. `alembic/env.py` reads `KB_DATA_DIR` (default `<repo_root>/data`). Tests in `test/test_db_init.py` cover migration round-trip, PRAGMA application, and trigger enforcement. Tasks B/C/D will build dispatch/wiki-edit repos and routes on this foundation.
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
