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

- Added the `cron-wrapup` skill and `kb-cron-wrapup.sh` wrapper for nightly KB operational summaries.
- Added optional global digest guidance under `knowledgebase-initialize/reference/optional-global-digest.md`.

### Changed

- Updated `knowledgebase-initialize` to include `cron wrap-up` as a required KB cron proposal and the morning digest as optional but recommended.
- Expanded the `cron-wrapup` summary contract with `Insights` and `Action Items` sections so daily wrap-ups surface user-facing KB signals, not only job status.
- Updated the cron-wrapup template and optional digest prompt to consume the expanded summary contract.
