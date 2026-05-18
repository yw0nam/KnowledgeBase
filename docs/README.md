# Documentation Index

Updated: 2026-05-18

## 1. Synopsis

- **Purpose**: Route humans and fresh-session agents to the right KnowledgeBase document.
- **I/O**: Question or task type -> document path to read first.

## 2. Core Logic

### Read Order

For a new human or agent, read in this order:

1. `CLAUDE.md`
2. `docs/architecture.md`
3. `docs/workflows/pipeline.md`
4. Task-specific workflow or reference document

For cron-based memory builds, read:

1. `CLAUDE.md`
2. `docs/workflows/cron-jobs.md`
3. `docs/workflows/usage-reports.md` if usage report jobs are enabled
4. `docs/workflows/periodic-memory-workflow.md`
5. `docs/workflows/pipeline.md`
6. `docs/reference/frontmatter.md`
7. `docs/reference/wiki-categories.md`
8. `docs/workflows/handoff-system.md`

### Directory Map

| Path | Role |
|---|---|
| `docs/architecture.md` | System layout and data boundaries |
| `docs/workflows/` | Step-by-step operating procedures |
| `docs/reference/` | Schemas, categories, commands, and lookup tables |
| `docs/db_informations/` | Database and reporting references |
| `docs/CLAUDE.md` | Document authoring rules |

### Document Types

Use `workflows/` for ordered execution steps. Use `reference/` for facts that agents look up while executing. Keep root `docs/` limited to index, architecture, and authoring guidance.

## 3. Usage

| Need | Read |
|---|---|
| Understand the repo | `docs/architecture.md` |
| Run raw-to-wiki pipeline | `docs/workflows/pipeline.md` |
| Configure cron jobs | `docs/workflows/cron-jobs.md` |
| Configure usage reports | `docs/workflows/usage-reports.md` |
| Run daily/weekly/monthly memory build | `docs/workflows/periodic-memory-workflow.md` |
| Handle handoff lifecycle | `docs/workflows/handoff-system.md` |
| Write valid frontmatter | `docs/reference/frontmatter.md` |
| Choose wiki category/path | `docs/reference/wiki-categories.md` |
| Run CLI commands | `docs/reference/commands.md` |

---

## Appendix

### A. PatchNote

- 2026-05-18: Added cron job workflow to memory build read order.
- 2026-05-18: Added usage report workflow for source-specific OpenCode/Hermes reports.
- 2026-05-18: Initial documentation index after workflow/reference split.
