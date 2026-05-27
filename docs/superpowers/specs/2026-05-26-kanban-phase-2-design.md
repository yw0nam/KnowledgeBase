# Kanban Phase 2 — Operational State DB + Decision Browser

**Date**: 2026-05-26
**Status**: Approved (brainstorming + reviewer LGTM complete, ready for implementation plan)
**Prior art**: [`2026-05-26-improvement-to-kanban-design.md`](2026-05-26-improvement-to-kanban-design.md) (Phase 1, shipped as PR #25)

## 1. Problem

Phase 1 shipped a "Send to Kanban" affordance that dispatches a pending improvement page to Hermes and persists the dispatch record as a `kanban_dispatches:` list inside the page's frontmatter. Two follow-on needs emerged immediately:

- **Operational state in markdown is fragile.** Dispatch records are not content; they are operational facts. Mixing them into frontmatter bloats the page metadata, complicates lint, and makes "what happened to this page" expensive to query.
- **The review console is queue-only.** Once a page is approved or rejected, it disappears from the UI. There is no way to revisit a decision, adjust its frontmatter (e.g. correct a misclassified `type` or add a missing tag), or see the dispatch/audit history without grepping markdown by hand.

Phase 2 lifts dispatch records into a small SQLite operational DB, removes the frontmatter coupling, and introduces a second console surface for browsing and editing previously-decided pages with an automatic audit trail.

## 2. Goals

1. **Single source of truth for operational state**: dispatch records, dispatch status transitions, and frontmatter-edit audits live in `data/db/state.db`, never in markdown.
2. **Markdown remains the SOT for content** (page bodies and frontmatter values). Phase 2 does NOT invert this; see §10.
3. **Decision browser**: a new "Decisions" tab in the review console lets the user filter, inspect, and edit previously-decided pages.
4. **Constrained editing**: frontmatter edits go through dropdowns (review_status, type, category) and chip add/remove (tags). No free-text frontmatter editing.
5. **Automatic audit**: every frontmatter edit through the console appends a row to `wiki_edits`. The user never writes audit entries manually.
6. **Workshop Bench discipline**: the new UI obeys PRODUCT.md and DESIGN.md — calm, precise, signal-accent ≤5%, no SaaS dashboard tropes.
7. **Inversion-safe inbound surface**: exactly one HTTP write endpoint requires Bearer auth (external worker status push). All other writes stay localhost-only.

## 3. Non-goals

- **Editing wiki bodies through the console**. Body editing belongs to Obsidian/Antigravity.
- **Type-change file moves**. Changing `type` from `entity` to `concept` would require moving the file across directories; Phase 2 rejects this with 409 and defers the rename workflow to Phase 2.x.
- **Concurrent-edit conflict detection**. Single-operator system; last-write-wins. The `wiki_edits` audit log captures conflict footprints if they ever happen.
- **Ingest HTTP API / MCP server**. Phase 3 will likely choose a file-based sync (gdrive / private git remote / syncthing) instead. The Phase 2 hardening of dispatch endpoints is deliberately NOT generalized to anticipate an HTTP ingest surface that may never exist (see §10).
- **Worker execution loop**. Hermes owns worker dispatch and execution. KB stays a promotion surface, not a workflow engine.
- **DB-as-SOT inversion**. Long-term direction, see §10 — not this PR.

## 4. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│ Vite/React frontend (kb-web)                                    │
│                                                                 │
│  Pending tab           Decisions tab           Dashboard tab    │
│   - QueuePage           - DecisionsPage         - existing      │
│   - DecisionDock        - PageInspector                         │
│     (Phase 1 dock)        (NEW push-rail)                       │
└─────────────────────────────────────────────────────────────────┘
                              ↕ HTTP (localhost)
┌─────────────────────────────────────────────────────────────────┐
│ FastAPI backend (kb-web)                                        │
│                                                                 │
│  /api/queue            /api/decisions        /api/dispatches    │
│  /api/dashboard        /api/pages/{stem}     /api/dispatches/   │
│  /api/kanban/boards    /api/pages/{stem}/        {id}/status    │
│                            frontmatter           ▲ Bearer auth  │
│                        /api/pages/{stem}/        only protected │
│                            timeline              endpoint       │
│                        /api/enums/categories                    │
└─────────────────────────────────────────────────────────────────┘
                              ↕                         ↕
              ┌───────────────────────┐     ┌──────────────────┐
              │ data/wiki/*.md        │     │ data/db/state.db │
              │ (SOT — content)       │     │ (operational     │
              │                       │     │  state +         │
              │ markdown + frontmatter│     │  audit log)      │
              └───────────────────────┘     └──────────────────┘
                              ↕
                  hermes kanban (subprocess)
                  - boards list
                  - card create / archive
```

Two new write surfaces:
- `PATCH /api/pages/{stem}/frontmatter` writes markdown atomically and inserts `wiki_edits` rows.
- `POST /api/dispatches/{id}/status` (Bearer required) updates the `dispatches` row.

All other writes are localhost-only.

## 5. Database Schema

SQLite at `data/db/state.db`. Engine via SQLAlchemy; migrations via Alembic. Connection-time pragmas:

```sql
PRAGMA journal_mode = WAL;
PRAGMA synchronous  = NORMAL;
PRAGMA foreign_keys = ON;
PRAGMA busy_timeout = 5000;
```

### 5.1 `dispatches`

```sql
CREATE TABLE dispatches (
    id              INTEGER PRIMARY KEY,
    page_stem       TEXT NOT NULL,
    page_path_at_dispatch TEXT NOT NULL,
    external_board_id  TEXT NOT NULL,
    external_task_id   TEXT NOT NULL,
    direction       TEXT,
    status          TEXT NOT NULL DEFAULT 'dispatched'
                    CHECK (status IN ('dispatched','in_progress','done','failed','cancelled','cancelling')),
    idempotency_key TEXT,
    created_at      TEXT NOT NULL
                    CHECK (created_at      LIKE '____-__-__T__:__:__+09:00'),
    dispatched_at   TEXT NOT NULL
                    CHECK (dispatched_at   LIKE '____-__-__T__:__:__+09:00'),
    last_status_at  TEXT
                    CHECK (last_status_at IS NULL OR last_status_at LIKE '____-__-__T__:__:__+09:00'),
    result_payload  JSON
                    CHECK (result_payload IS NULL OR json_valid(result_payload)),
    UNIQUE (external_board_id, external_task_id)
);
CREATE UNIQUE INDEX ux_dispatches_idempotency_key
    ON dispatches(idempotency_key) WHERE idempotency_key IS NOT NULL;
CREATE INDEX ix_dispatches_status_dispatched_at
    ON dispatches(status, dispatched_at DESC);
CREATE INDEX ix_dispatches_page_stem_dispatched_at
    ON dispatches(page_stem, dispatched_at DESC);
```

**Field notes:**
- `external_board_id` / `external_task_id` — named generically (not `board_slug`/`task_id`) so future task-system swaps don't require a schema migration. No `TaskSystemAdapter` interface ships in this PR; the helper module simply calls `hermes` directly.
- `page_path_at_dispatch` — snapshot for debugging (e.g. if the page was later moved, this records the path at dispatch time).
- `idempotency_key` — optional client-provided UUID. Same key replayed → existing row returned with HTTP 200. Replay protection lives forever via the row; explicit TTL is not modeled (single-operator system, replay window is seconds-to-minutes).
- `status` enum — `cancelling` is the transient state between user-requested cancel and confirmed Hermes archive. A row stuck in `cancelling > 1h` should appear as anomalous on the dashboard (operational concern, not enforced in schema).
- `result_payload` — JSON column for worker-reported result data (file paths, summaries, exit codes). Schema-free; KB stores but does not interpret.

### 5.2 `wiki_edits`

```sql
CREATE TABLE wiki_edits (
    id              INTEGER PRIMARY KEY,
    page_stem       TEXT NOT NULL,
    field           TEXT NOT NULL
                    CHECK (field IN ('review_status','type','category','tags')),
    old_value       JSON CHECK (old_value IS NULL OR json_valid(old_value)),
    new_value       JSON CHECK (new_value IS NULL OR json_valid(new_value)),
    edited_at       TEXT NOT NULL
                    CHECK (edited_at LIKE '____-__-__T__:__:__+09:00'),
    source          TEXT NOT NULL DEFAULT 'console'
                    CHECK (source IN ('console','migration'))
);
CREATE INDEX ix_wiki_edits_page_stem_edited_at
    ON wiki_edits(page_stem, edited_at DESC);
CREATE INDEX ix_wiki_edits_review_status_transitions
    ON wiki_edits(edited_at) WHERE field = 'review_status';

CREATE TRIGGER trg_wiki_edits_no_update
BEFORE UPDATE ON wiki_edits
BEGIN SELECT RAISE(ABORT, 'wiki_edits is append-only'); END;

CREATE TRIGGER trg_wiki_edits_no_delete
BEFORE DELETE ON wiki_edits
BEGIN SELECT RAISE(ABORT, 'wiki_edits is append-only'); END;
```

**Field notes:**
- `field` enum is pure frontmatter — `review_status`, `type`, `category`, `tags`. Dispatch status transitions do NOT create `wiki_edits` rows (they're in `dispatches`). The page-level timeline endpoint UNIONs both sources.
- `source` enum: `console` (user-driven edits through the UI) and `migration` (Phase 2 backfill). External edits (manual md edit, cron, git pull) are NOT logged here; `data/log.md` continues to cover those.
- Triggers enforce append-only at the storage layer. Application-layer guards are belt; triggers are suspenders.
- Timestamps must match `____-__-__T__:__:__+09:00` (KST with explicit offset). A stray UTC `Z`-suffixed row would silently break range queries six months in.

## 6. API Contract

### 6.1 Existing endpoints (Phase 1 — wire-compat preserved)

```
GET /api/queue?status=pending_for_approve
GET /api/pages/{stem}
GET /api/dashboard
GET /api/kanban/boards
```

### 6.2 Existing endpoint with behavior change

```
POST /api/pages/{stem}/send-to-kanban
```

Changes:
- Optional `Idempotency-Key` header (client-generated UUID). Same key replayed → existing dispatch row returned, HTTP 200.
- No longer writes the `kanban_dispatches` frontmatter list. Inserts a `dispatches` row instead.
- Response shape: `{id, external_task_id, external_board_id, dispatched_at}` (was `{task_id, board_slug, dispatched_at}` in Phase 1; the frontend migrates with the rename).

### 6.3 New dispatch endpoints

```
GET /api/dispatches?page_stem=&status=&since=&limit=
Response: {items: [DispatchRecord], total}
```
Cursor pagination (`since` is the last `dispatched_at` seen; `limit` defaults to 50, max 200).

```
POST /api/dispatches/{id}/status      [BEARER REQUIRED]
Body: {
  status: 'in_progress' | 'done' | 'failed' | 'cancelled',
  result_payload?: {...},
  occurred_at?: 'YYYY-MM-DDTHH:MM:SS+09:00'
}
```
Server stamps `last_status_at = server_now()` regardless of `occurred_at` (informational only — workers are localhost in Phase 2, drift unmodeled).

Allowed transitions (enforced in code; 409 on violation):
```
dispatched   → in_progress | done | failed | cancelling
in_progress  → done | failed | cancelling
done         → (terminal)
failed       → (terminal)
cancelling   → cancelled
cancelled    → (terminal)
```
Monotonic `last_status_at` enforcement: if a status push arrives with `occurred_at <= last_status_at`, return 409 ("status_out_of_order"). Catches retry reordering.

```
POST /api/dispatches/{id}/cancel        [localhost only]
```
Two-state machine:
1. UPDATE `dispatches.status = 'cancelling'`.
2. Call `hermes kanban archive <external_task_id>`.
3. On success → UPDATE `status = 'cancelled'`, respond 200.
4. On Hermes failure → row stays `cancelling`, respond **502** with `{db_state: 'cancelling', external_error: '...'}`.

Force-escape:
```
POST /api/dispatches/{id}/cancel?force=true
```
Flips DB to `cancelled` without calling Hermes. Use only when the operator knows the card is already archived externally.

### 6.4 New decision-browser endpoints

```
GET /api/decisions?status=&type=&category=&source=&edited_since=&page=&per_page=
Response: {
  items: [{
    stem, path, type, category, tags, review_status,
    sources, captured_at, last_edited_at,
    dispatch_summary: {count, last_status} | null
  }],
  total, page, per_page
}
```
- All query params multi-valued (`?status=approved&status=rejected`).
- `dispatch_summary.last_status` aggregation rule: latest by `dispatches.last_status_at DESC`, ties broken by `dispatched_at DESC`.
- `last_edited_at` derivation: `COALESCE(MAX(wiki_edits.edited_at WHERE page_stem=?), <frontmatter captured_at>)`. If a page has no console-driven edits yet, `captured_at` is the fallback.
- Page-based pagination (`page` 1-indexed, `per_page` 50 default, max 200).
- **Read path**: on-demand markdown directory scan + frontmatter parse. Acceptable for current corpus (~300 pages, sub-second on SSD). Index materialization deferred — see §10.

```
PATCH /api/pages/{stem}/frontmatter
Body (merge patch — absent = unchanged, [] = clear):
  {
    review_status?: 'pending_for_approve' | 'approved' | 'rejected' | 'not_processed',
    type?: 'entity' | 'concept' | 'decision' | 'question'
         | 'improvement' | 'checklist' | 'summary',
    category?: '<enum-from-wiki-categories.md>',
    tags?: ['tag1', 'tag2', ...]     // full replacement
  }
```

Write pipeline (order is load-bearing):
1. Read current file → parse frontmatter.
2. Apply patch in memory → serialize candidate content.
3. Run `kb-lint-wiki` against candidate (stdin or temp path, NOT the real file).
4. If lint passes: `write candidate to {path}.tmp` → `fsync` → `os.replace(tmp, path)`.
5. Insert `wiki_edits` rows (one per changed field) in a single DB transaction; commit.

Failure modes:
- Lint failure → 409 with `{detail, lint_errors: [...]}`; file untouched.
- `type` change requires file rename (e.g. `entities/` ↔ `concepts/`) → 409 "type change requires manual rename" (deferred to Phase 2.x).
- Atomic rename succeeds but DB commit fails → respond **500** with `{detail: "frontmatter written, audit failed", file_written: true}`. The file is updated; the audit row is missing for that change. Recovery: client retries the same PATCH — step 1 reads the current (already-updated) file, detects no diff to apply, returns 200 with `edits: []`. The audit gap remains; future `kb-reindex` (out of scope) can reconcile by re-parsing files vs `wiki_edits` history.

PATCH is idempotent: if the patched values equal current file state, no file write and no `wiki_edits` row; response is 200 with `edits: []`.

Response:
```
200 {
  stem,
  frontmatter: {...},
  edits: [{field, edited_at}, ...]
}
```

```
GET /api/pages/{stem}/edits?since=&limit=
GET /api/pages/{stem}/timeline?since=&limit=
GET /api/enums/categories?type=<wiki_type>
```
- `edits` returns `wiki_edits` rows for this page.
- `timeline` UNIONs `wiki_edits` and `dispatches` status transitions, sorted descending.
- `enums/categories` returns the categories valid for a given wiki type. Source: `docs/reference/wiki-categories.md`.

### 6.5 Auth model

- Default: localhost-only, no auth (Phase 1 stance preserved).
- Exception: `POST /api/dispatches/{id}/status` requires `Authorization: Bearer ${KB_API_TOKEN}`.
- If `KB_API_TOKEN` env var is unset, the status endpoint returns **500** `{detail: "KB_API_TOKEN env var not set; status push disabled"}`. Config error, not transient — no retry implied.

### 6.6 Error taxonomy

| HTTP | Meaning |
|---|---|
| 400 | Bad payload (enum mismatch, malformed stem) |
| 401 | Bearer missing/wrong (status push only) |
| 404 | Dispatch or page not found |
| 409 | Lint failure, frontmatter parse error, type change requires rename, status transition violation, monotonic occurred_at violation |
| 422 | Pydantic validation |
| 500 | KB_API_TOKEN unset (config error) |
| 502 | Hermes unreachable, Hermes archive failed during cancel |

## 7. Frontend

### 7.1 Navigation

```
Pending (n)    Decisions    Dashboard
```
- "Pending" — renamed from Phase 1's QueuePage display label; same data (review_status=pending_for_approve). `(n)` is the live count.
- "Decisions" — new tab. The Decisions browser surface.
- "Dashboard" — existing.

### 7.2 Decisions tab — Tab + Filter (Pattern X)

```
┌─────────────────────────────────────────────────────────────────┐
│ Pending  [Decisions]  Dashboard                                 │
├─────────────────────────────────────────────────────────────────┤
│ Approved · Rejected · Dispatched · Unprocessed                  │
│ ↑ active tab subtitle: "Pages sent to Kanban that haven't       │
│   returned a status." (ink-muted hairline below tab row)        │
│                                                                 │
│ Type ▾   Category ▾   Source ▾   Edited ▾                       │
│ (active filter chips: hairline Signal border, label weight bump)│
│ ↑ "Clear all (N)" hairline link appears top-right when ≥2 active│
├─────────────────────────────────────────────────────────────────┤
│ stem                          type     category     edited      │
│ ─────────────────────────────────────────────────────────────── │
│ hermes-zombie-session         entity   system-ops   2d          │
│ wiki-write-model              concept  process      14h         │
│ promote-cron-flow             concept  process      3d          │
│                                                                 │
│ 1–50 of 312                            ‹ 1 2 3 4 5 6 7 ›       │
└─────────────────────────────────────────────────────────────────┘
   ↑ row click opens PageInspector (right-side push-rail)
```

Rules:
- Tabs cover `review_status` only. There is no "All" tab; if filters narrow further, the active tab gets an inline "× clear" hairline.
- Filters are multi-value, custom dropdown primitive (NOT native `<select>` — consistent vocabulary with the inspector).
- URL queryparams reflect tab + filters + selected stem. Reload restores state.
- Default sort: `last_edited_at DESC`. Header-click sort deferred to Phase 2.1.
- Mono font on `stem` and `type` columns (DESIGN.md Mono-for-Strings).
- Tabular figures on `edited` column and pagination ("1–50 of 312").

### 7.3 PageInspector (NEW primitive, right push-rail)

Distinct from DecisionDock — separate primitive, separate name, separate intent. The Phase 1 dock stays for queue-action decisions on the Pending tab.

```
┌─ Page list (resized to 1fr) ──────┐┌─ PageInspector (420px) ────────┐
│ hermes-zombie-session             ││ entities/hermes/2026-05/        │
│ wiki-write-model                  ││   hermes-zombie-session.md      │
│ promote-cron-flow                 ││ Open source ↗                   │
│ …                                 │├─────────────────────────────────┤
│                                   ││ review_status                   │
│                                   ││   [approved              ▾]     │
│                                   ││                                 │
│                                   ││ type                            │
│                                   ││   [entity                ▾]     │
│                                   ││                                 │
│                                   ││ category                        │
│                                   ││   [system-ops            ▾]     │
│                                   ││                                 │
│                                   ││ tags                            │
│                                   ││   [hermes] [zombie] [daemon]    │
│                                   ││   + add tag                     │
│                                   ││                                 │
│                                   ││ [Save (cmd+s)]                  │
│                                   │├─────────────────────────────────┤
│                                   ││ Edit history · 12 edits ·       │
│                                   ││   last 14h ago             ▾    │
│                                   ││  2026-05-26 14:23  review_status│
│                                   ││    pending → approved           │
│                                   ││  2026-05-26 14:23  category     │
│                                   ││    — → system-ops               │
│                                   ││  2026-05-25 09:12  status       │
│                                   ││    dispatched → done            │
│                                   ││  Show all 12                    │
│                                   │├─────────────────────────────────┤
│                                   ││ cmd+s save · esc close · r      │
│                                   ││   reject · a approve · k        │
│                                   ││   send to kanban                │
└───────────────────────────────────┘└─────────────────────────────────┘
                                       ↑ push-rail: drag-handle 4px,
                                         col-resize, hairline visual.
                                         localStorage persists width.
                                         <1100px viewport = overlay.
```

**Rules:**
- Two zones only — frontmatter editor + edit history. **No body preview.**
- Header is one mono line (stem) + an "Open source" link (opens markdown in OS handler, never renders in-app). No breadcrumb, no metadata stack.
- Edit history rows arrow-anchored: `{timestamp · tabular} {field}: {old} → {new}`. No user column.
- Default 3 most-recent edits visible; "Show all 12" expands inline. Expanded history caps at 50% of inspector height with internal scroll so Save never gets pushed off-screen.
- Save button sits at the bottom of the frontmatter zone, not in the sticky footer. Save commits the form context it lives in.
- Dirty state on Save: leading mono middot `·` at tabular width.
- Filter and inspector dropdowns share a single custom dropdown primitive (NOT native `<select>`).
- Tag chips: chip + inline input. Enter/Comma confirms a chip. `×` on hover removes. Backspace on empty input removes last chip. Duplicates silently deduped. Save sends the full new tag list (PATCH semantics: presence of `tags` = full replacement).
- Type-change cascade: if the new `type` invalidates the current `category`, inline warning under category and Save disabled until user picks a valid one.
- Type-change requiring rename: same gate, plus inline link to "Open source" for manual rename.
- Concurrency: last-write-wins. No ETag/If-Match. The audit log captures any clobber after the fact.

### 7.4 Keyboard

- `cmd+s` / `cmd+enter` → Save (modifier always present, safe over inputs).
- `r` reject, `a` approve, `k` send-to-kanban — scoped to "no input focused". Footer hint row dims when an input has focus.
- `j` / `k` — row nav in the Decisions table.
- `g d` / `g p` / `g a` — go to Decisions / Pending / Dashboard (Linear pattern, leader timeout 200–300ms).
- `?` — opens shortcut overlay (centered card on low-opacity scrim, no blur, opacity-fade transition only).
- `esc` — closes inspector. Dirty + esc → confirm dialog.

### 7.5 Empty / error states

Lint-grade honesty, no illustrations:
- Empty list: `"No approved pages match these filters. (312 approved pages total.)"` + Reset link.
- 404-after-move: `"Page no longer at this path. (Last seen at <path>, moved 2h ago — see edit history.)"` + close button.
- Lint failure on Save: inline error under the affected field. Form state preserved.

### 7.6 File scope (frontend)

```
NEW:
  frontend/src/DecisionsPage.tsx
  frontend/src/components/PageInspector.tsx
  frontend/src/components/PageInspector.module.css
  frontend/src/components/DecisionsFilter.tsx
  frontend/src/components/DecisionsList.tsx
  frontend/src/components/FrontmatterEditor.tsx
  frontend/src/components/TagChips.tsx
  frontend/src/components/EditTimeline.tsx
  frontend/src/components/Dropdown.tsx           (shared custom dropdown primitive)
  frontend/src/components/KeyboardHelpOverlay.tsx
  frontend/src/hooks/useUrlFilters.ts
  frontend/src/hooks/useLeaderShortcut.ts

EXTENDED:
  frontend/src/api.ts             (decisions, patch, timeline, enums, dispatch list/status/cancel)
  frontend/src/types.ts           (FrontmatterPatch, Decision, TimelineEvent, DispatchRecord)
  frontend/src/QueuePage.tsx      (nav label, Decisions link)
  frontend/src/components/DecisionDock.tsx       (label change only; remains the pending-tab primitive)
  frontend/src/components/Frontmatter.tsx        (SKIP_KEYS updated — kanban_dispatches no longer present)
```

## 8. Migration

Phase 1 left a single `kanban_dispatches` entry in `data/wiki/improvements/2026-05/hermes-zombie-session.md` (smoke test). The Phase 2 migration:

1. Alembic migration creates `dispatches`, `wiki_edits`, and indexes/triggers.
2. A one-shot CLI `kb-migrate-kanban-dispatches` reads every wiki file, finds `kanban_dispatches` frontmatter lists, inserts one `dispatches` row per entry with `created_at = dispatched_at = <original timestamp>`, and removes the `kanban_dispatches` key from the file.
3. The CLI is idempotent: running twice produces the same DB state (`UNIQUE(external_board_id, external_task_id)` blocks duplicate inserts; missing frontmatter key is a no-op).
4. Migration is operator-invoked (not automatic on app start). Documented in CHANGELOG.

## 9. Testing

### 9.1 Backend pytest — 16 tests

```
test/test_db_init.py                  (3)
  - Alembic up → down → up round-trip
  - PRAGMAs applied on connect (WAL, foreign_keys, busy_timeout, synchronous)
  - wiki_edits UPDATE/DELETE triggers raise

test/test_dispatch_repo.py            (5)
  - Idempotency-Key replay returns existing dispatch row
  - status push: monotonic occurred_at violation → 409
  - status push: transition graph violation → 409
  - cancel: dispatched → cancelling → cancelled state machine
  - UNIQUE(external_board_id, external_task_id) violation → IntegrityError

test/test_route_dispatches.py         (3)
  - POST status: bearer missing → 401
  - POST cancel: Hermes archive failure → 502 + DB stays 'cancelling'
  - POST send-to-kanban: DB insert + frontmatter unchanged (Phase 1 regression guard)

test/test_route_decisions.py          (4)
  - PATCH frontmatter: lint failure → 409 + file unchanged (rollback proof)
  - PATCH frontmatter: single field → atomic rename + wiki_edits row inserted (commit ordering verified)
  - PATCH frontmatter: os.replace success but simulated DB commit failure → 500 + file_written=true; retry returns 200 with edits=[] (idempotency)
  - PATCH type change requiring rename → 409

test/test_migration_backfill.py       (1)
  - Backfill CLI idempotency (running twice produces the same DB state)
```

### 9.2 Frontend vitest — 10 tests

```
PageInspector.test.tsx     (2)
  - row click opens, ESC closes
  - dirty + ESC → confirm dialog

FrontmatterEditor.test.tsx (5)
  - dropdown change → dirty flag
  - type change → invalid-category warning + Save disabled
  - tag chip add (Enter) + remove (× click)
  - lint error inline + form state preserved
  - PATCH body: only changed fields + tags full replacement

useUrlFilters.test.ts      (2)
  - filter change → URL update
  - URL → filter state restoration round-trip

EditTimeline.test.tsx      (1)
  - arrow-anchored row format (`field: old → new`)
```

### 9.3 Explicitly not automated

- Enum exhaustion (one branch per enum covers the mechanism)
- Pagination control variations, j/k nav, push-rail drag, localStorage width persistence, `?` overlay rendering — verified in manual smoke
- Empty-state copy and header text — snapshot brittleness for negligible coverage gain
- DB list filter combination matrix
- `enums/categories` per-type variations

### 9.4 Manual smoke (pre-merge, Playwright MCP)

1. Send to Kanban → confirm DB row.
2. `curl` status push → row visible in Decisions tab.
3. Click row → PageInspector opens → change `review_status` → confirm `wiki_edits` row + markdown updated.
4. `type` change requiring rename → confirm 409 inline warning.
5. `cmd+s` save + `?` overlay behavior.

### 9.5 Lint gates

- `./scripts/lint.sh` continues to gate the Python and frontend portions.
- Add: `uv run alembic check` to detect schema drift.

## 10. Future direction (memo, NOT this PR)

The long-term plan, captured here so future PRs don't have to rediscover it:

- **DB-as-SOT inversion** — `state.db` becomes the canonical store for frontmatter values; `data/wiki/*.md` frontmatter blocks become rendered views. `kb-lint-wiki` migrates from "read markdown, validate" to "read DB, validate; markdown is regenerated."
- **Read path optimization** — when Decisions list reads outgrow on-demand markdown parsing, introduce a `pages_index` denormalized read view in DB, populated on PATCH and re-buildable via a `kb-reindex` CLI. Markdown stays SOT until the inversion PR.
- **External access surface** — Phase 3 will likely choose a file-based sync (gdrive / private git remote / syncthing) for ingest, NOT an HTTP ingest API or MCP server. Status push remains the only HTTP write endpoint requiring auth.

These directions are out of scope for Phase 2 and should not influence Phase 2 implementation choices except by keeping the existing schema/API simple enough to evolve.

## 11. Implementation order

The spec is one document; the implementation is two PRs from this spec.

**Phase 2a — DB + dispatch ledger**:
- Schema (§5), Alembic migration, repo helpers
- New endpoints in §6.3 + the §6.2 behavior change
- Backfill CLI (§8)
- BE tests from §9.1

**Phase 2b — Decision browser**:
- New endpoints in §6.4
- Frontend file scope (§7.6)
- FE tests from §9.2
- Manual smoke (§9.4)

Each PR runs `./scripts/lint.sh` + frontend gates green before merge. Phase 2b depends on Phase 2a.
