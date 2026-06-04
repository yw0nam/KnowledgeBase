# DB-Canonical Memory Architecture

Updated: 2026-06-04

## 1. Synopsis

- **Decision**: Promote `data/db/state.db` from operational sidecar to the
  canonical knowledge store.
- **Role of Markdown**: Markdown remains an import/export format and human
  inspection surface, not the long-term source of truth once migration is
  complete.
- **Reason**: Multi-machine, multi-session operation needs transactional writes,
  queryable metadata, stable audit history, and a sync strategy that is not built
  around Git merge conflicts in generated knowledge files.

## 2. Target Model

The DB owns durable memory:

| Table | Role |
|---|---|
| `pages` | Canonical wiki page record: slug, title, body markdown, frontmatter JSON, review state, type/category/tags payload. |
| `raw_sources` | Immutable captured evidence, replacing `data/raw/` as the canonical source store. |
| `page_sources` | Many-to-many citation links between pages and raw sources. |
| `page_revisions` | Append-only page revision ledger for body/frontmatter changes. |
| `dispatches` | Existing external workflow dispatch state. |
| `wiki_edits` | Former legacy frontmatter edit audit, now removed. `page_revisions` is the sole audit table. |
| `metrics` | Operational metrics (promotions, rejections, TTL sweeps, page counts) for dashboard and reporting. |

Markdown exports are generated from DB rows. They may still be committed,
searched, or opened in external tools, but a Markdown file no longer wins over a
DB row when the two disagree.

## 3. Migration Strategy

1. ✅ Add canonical schema beside the current operational tables.
2. ✅ Write an importer from the existing `data/raw/` and `data/wiki/` tree into the
   canonical tables.
3. ✅ Move read endpoints from Markdown scans to DB queries via `/api/queue`,
   `/api/pages/{slug}`, and `/api/dashboard`.
4. ✅ Move mutation endpoints (approve/reject/frontmatter edits) into one DB
   transaction that also appends `page_revisions`.
5. ✅ Add Markdown export as an explicit command. Export is allowed to overwrite
   generated files because it is derived output.
6. ✅ Retire the PR-based nested `data/` Git sync. Git-based sync is fully
   deprecated; `data/` is a generated export directory.

## 4. Sync Direction

The preferred production-like topology is a single writer-capable DB service
(for example Postgres) accessed by all machines. Local SQLite remains useful for
development and single-machine operation, but SQLite file replication is not a
multi-writer sync design.

Offline-first sync is a separate product decision. If it becomes required, use
an explicit event-log replication design rather than treating Git or Litestream
as conflict resolution for concurrent writers.

## 5. Guardrails

- Do not create a dual-source-of-truth system. During migration, every code path
  must state whether Markdown or DB wins.
- Do not add new query surfaces by scanning Markdown if the same data already
  exists in canonical tables.
- Keep append-only history in the DB. Human-readable logs are exports, not audit
  authority.
- Keep raw source immutability at the table level, not only in linter rules.

## Appendix

### A. PatchNote

- 2026-06-04: Initial DB-canonical architecture decision.
