# DB-as-SOT Inversion — Design (DRAFT v2)

Status: DRAFT — incorporated round-1 specialist reviews (Database Optimizer, Backend Architect); awaiting confirming LGTM, then user approval.
Date: 2026-05-27

## 0. Locked decisions (do not relitigate)

1. **Full inversion now.** Validation/experimentation phase, not production ops. No burn-in period; fast iteration beats the staged "mirror-first" arc.
2. **Edit model = Option 3 "sidecar".** Frontmatter is single-home canonical in `state.db`. The markdown **body** stays file-SOT. The `.md` file = hand/skill-authored body **plus a generated, read-only frontmatter block** for Obsidian viewing and git diffs. The file block is a *view*, never canonical — no dual-home, no reconciliation loop.
3. **Scope v1 = wiki frontmatter only** (`entities/`, `concepts/`, `decisions/`, `questions/`, `improvements/`, `checklists/`, `summaries/`). The `[[wikilink]]` graph stays body-derived (file-scanned by lint). `raw/` stays file-SOT. `index` pages (`INDEX.md`, `_index.md`) are generated listings and are **not** rows in `pages`.
4. **Future DB-canonical targets are documented, schema is additive.** A future `links` edge table (body-derived wikilinks) and a future read-only `raw_files` mirror MUST eventually live in the DB. v1 schema is designed so both attach as new tables with zero migration of the `pages` schema. The v1 `page_aliases` table (§2.4) is the one forward-compat dependency that must land now so future link resolution can match aliases.

## 1. Synopsis

- **Today:** markdown is SOT; `state.db` holds only operational state (`dispatches`, `wiki_edits`). `lint_wiki.py` and the FastAPI read paths parse markdown frontmatter on-demand.
- **After:** `state.db` is canonical for wiki frontmatter. Body stays file-SOT. The `.md` frontmatter block is regenerated from the DB. Frontmatter lint and console reads query SQL; body/link lint still scans files.
- **Operator rule:** *Body is yours to edit freely. Frontmatter is managed — change it through the console or the `kb-page` CLI. Hand-edited frontmatter in a file is silently overwritten on next render.*

## 2. Schema (state.db additions)

New tables alongside `dispatches` / `wiki_edits`. SQLite + SQLAlchemy + Alembic; match the raw-SQL `op.execute` style and PRAGMAs of migration `53cdbd2e163d`. `pages` mirrors **`data/wiki/` only** — rejected pages move out of the tree (§4.4) and have no row.

### 2.1 `pages`

```sql
CREATE TABLE pages (
    id            INTEGER PRIMARY KEY,
    stem          TEXT NOT NULL UNIQUE,           -- wikilink target key [[stem]]
    rel_path      TEXT NOT NULL UNIQUE,           -- current path under data/wiki/
    type          TEXT NOT NULL
                  CHECK (type IN ('entity','concept','decision','question',
                                  'improvement','checklist','summary')),
    subtype       TEXT                            -- summary: weekly|monthly|daily; else NULL
                  CHECK (subtype IS NULL OR subtype IN ('weekly','monthly','daily')),
    category      TEXT,                            -- open string, nullable
    review_status TEXT
                  CHECK (review_status IS NULL OR
                         review_status IN ('not_processed','pending_for_approve','approved')),
    period_start  TEXT CHECK (period_start IS NULL OR period_start LIKE '____-__-__%'),
    period_end    TEXT CHECK (period_end   IS NULL OR period_end   LIKE '____-__-__%'),
    created       TEXT NOT NULL,                   -- date OR datetime; loose CHECK only
    updated       TEXT NOT NULL,
    extra         JSON CHECK (extra IS NULL OR json_valid(extra)),
    CHECK (
      (type IN ('entity','concept','decision','improvement','checklist','question')
         AND review_status IS NOT NULL)
      OR (type = 'summary' AND review_status IS NULL)
    )
);
CREATE INDEX ix_pages_type_review_status ON pages(type, review_status);
CREATE INDEX ix_pages_review_status ON pages(review_status) WHERE review_status IS NOT NULL;
CREATE INDEX ix_pages_type_category  ON pages(type, category);
CREATE INDEX ix_pages_period_end ON pages(period_end DESC) WHERE type = 'summary';
```

- **Typed common columns + one `extra` JSON** for per-type long-tail. Not EAV, not per-type tables, not a 40-column wide table.
- `extra` holds: improvement `kind/observed_at/domain/severity/issue_status` + `related[]`; summary `week`/`month` display labels. Improvement enums stay in `extra` (improvement-only, lint-checked, never console-filtered) — do not promote.
- No denormalized `title` column: the display title is the body H1; `stem` is identity.
- `created`/`updated` accept both `YYYY-MM-DD` and full datetime (templates use both) — loose prefix CHECK, never the rigid `+09:00` form used by `dispatches`.

### 2.2 `page_tags`
```sql
CREATE TABLE page_tags (
  page_id INTEGER NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
  tag     TEXT NOT NULL,
  UNIQUE(page_id, tag)
);
CREATE INDEX ix_page_tags_tag ON page_tags(tag);
```

### 2.3 `page_sources`
```sql
CREATE TABLE page_sources (
  page_id INTEGER NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
  source  TEXT NOT NULL,                          -- data/-relative raw path
  UNIQUE(page_id, source)
);
CREATE INDEX ix_page_sources_source ON page_sources(source);
```

### 2.4 `page_aliases` (forward-compat for future `links`)
```sql
CREATE TABLE page_aliases (
  page_id INTEGER NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
  alias   TEXT NOT NULL,
  UNIQUE(page_id, alias)
);
CREATE UNIQUE INDEX ux_page_aliases_alias ON page_aliases(alias);
```
`aliases` (entity/concept templates) are wikilink resolution targets. The global-unique index enforces alias↔alias non-collision; lint adds alias↔stem non-collision. Without this table now, the future `links` table would JSON-scan `pages` to resolve `[[alias]]`. `related` (improvement-only) stays in `extra`.

### 2.5 Multi-valued FK rule
Join tables FK on immutable `pages.id` (not `stem`, which can change on retype) with `ON DELETE CASCADE`. SQLite does not auto-index FK child columns — the per-value indexes above are required for reverse lookup and cascade.

### 2.6 ORM + audit
- Add `Page`, `PageTag`, `PageSource`, `PageAlias` to `models.py`, export from `db/__init__.py __all__` (migration is SOT; models mirror).
- **Widen `wiki_edits.field` CHECK** (currently `review_status|type|category|tags`) to also allow `sources|aliases|subtype|period_start|period_end|extra` — otherwise audit rows for the new editable fields are rejected. Separate Alembic op in the same PR.

### 2.7 Future (documented, NOT built in v1)
- `links(src_page_id FK→pages.id CASCADE, dst_stem TEXT, …)` — body-derived edges; resolves against `stem` ∪ `page_aliases.alias`. Zero `pages` migration.
- `raw_files(...)` — read-only mirror of `raw/` frontmatter; fully independent table. `raw/` stays file-SOT/immutable.

## 3. Page identity & path mapping

- `stem` is the wikilink key, globally unique (lint enforces).
- `rel_path` is derived from type/category/subject/date conventions; UNIQUE (one file per path).
- `id` is the stable identity across rename/recategorize. Join FKs are on `id`.
- A `type`/`category` change that alters `rel_path` is performed by `kb-page set` (§4.2): it updates `stem`(if changed)/`rel_path`/all join rows **in one transaction**, `git mv`s the body file, re-renders the block, and emits a `wiki_edits` row. This is where the Phase-2 "type change = 409" gap is closed.

## 4. Write paths (one shared core)

**Single write core (mandatory, not optional):**
```
apply_frontmatter_change(session, stem, changes, *, source, move=None) ->
   updates pages (+ join rows) → appends wiki_edits → (git mv if move) → re-renders block → returns final frontmatter
```
Both the console PATCH and the `kb-page` CLI call this one function. Re-implementing the ordering (mirror-lint → DB write → audit → render → recovery) in two places is a guaranteed divergence bug; the current 100+-line `pages.py` PATCH pipeline is refactored into this core.

### 4.1 Console PATCH
`PATCH /api/pages/{stem}` → `apply_frontmatter_change(..., source="console")`. Body untouched.

### 4.2 `kb-page` CLI (skill + manual interface)
- `kb-page create --type … --stem … [--category …] [--field k=v …] [--tag …] [--source …] [--alias …] --body-file PATH` → insert row + write body file + render block.
- `kb-page set <stem> --field k=v [--add-tag/--rm-tag] [--add-source/--rm-source] [--add-alias/--rm-alias]` → calls the core; when a field change alters `rel_path` (type/category), the core performs the `git mv` (no separate `move` verb).
- `kb-page render [<stem> | --all]` → idempotent regenerate of the block(s) from DB. Primarily an internal/repair primitive (called by `import`, the pre-commit hook, and after manual DB edits); not a daily verb.
- `kb-page import [<path> | --all]` → one-time / repair ingest (§6); idempotent upsert-by-stem.

Skills stop hand-writing frontmatter YAML: they write the **body** file and call `kb-page`. SKILL.md contracts updated (§7.2 blast radius).

### 4.3 Obsidian (hand edit)
Body edits flow naturally (body is file-SOT). The frontmatter block is generated read-only — hand edits are **silently overwritten** on next render. No lint ERROR is needed for block edits (render already enforces it; the condition is unobservable in the commit-gating path — see §6.1). A file with **no `pages` row** (hand-created page) is the real failure and is an ERROR (§6.1).

### 4.4 Rejection (stays in `kb-wiki-review`)
`approve`/`reject`/`promote` keep their `kb-wiki-review` CLI interface — they have side effects beyond a field flip (`reject` `git mv`s to `data/rejected/` and stamps `rejected_at`/`rejected_by`; appends a feedback body section). They route their frontmatter write through the shared core (§4) but are not folded into `kb-page set`. On reject: `git mv` out of `data/wiki/` → **delete the `pages` row** (cascade clears joins) → `wiki_edits` audit row keyed by the `stem` **string** (not a `page_id` lookup, which would fail post-delete; `wiki_edits.page_stem` is free TEXT with no FK). `data/rejected/` is not mirrored.

## 5. Render mechanism

- `kb-page render` regenerates the top-of-file frontmatter block from the DB row, deterministic key order (stable, clean diffs).
- **Marker:** an in-YAML comment line (`# managed-by: kb-page`) inside the `---` fences. It survives `yaml.safe_load` round-trip and never lands in the body (an HTML comment outside the fences would trip body checks). The marker is cosmetic/human-facing — no parser depends on it.
- **Trigger:** auto-render the affected file on every DB write (console + CLI). A git pre-commit hook runs `kb-page render --all` + lint as the backstop (§6.1).

## 6. Lint migration (split) + reconciliation

### 6.1 Reconciliation checks (replace the proposed "block drift" check)
Auto-render (§5) makes "file block ≠ DB render" structurally unobservable in the commit-gating path, so that check is **cut**. The observable, meaningful checks are:
- **Orphan file** — a `.md` under `data/wiki/` with no `pages` row → ERROR ("hand-created page; author via console/`kb-page`, or run `kb-page import`"). Catches skills/humans that bypass the DB.
- **Missing body** — a `pages` row whose body file is absent → ERROR.
- **Path drift** — resolve the file by `stem` scan (as `resolve_stem` does today); if the found path ≠ `rel_path`, ERROR (someone hand-`git mv`'d the body). This is the only drift that is actually observable.

### 6.2 Per-check assignment
| check | after inversion |
|---|---|
| #5 frontmatter: required-fields + enum membership | **DB-driven** value validation (reports `rel_path`). Format sub-checks (quoted `type:`, inline `sources: [...]`) are **retired** — render guarantees their absence. |
| #12 improvement enums | **DB-driven** (validate `extra`, report `rel_path`) |
| #10 orphan pages | **hybrid** — exemption predicates (`review_status != approved`, `type == summary`) → SQL; `[[link]]` inbound graph → file scan |
| #11 INDEX.md / `_index.md` sync | **hybrid** — listings/status from DB; disk presence from files |
| #1–4 wikilinks, .md-ext, self-link, placeholders | file-based (body) — unchanged |
| #6–9 empty section, empty rels, stub length | file-based (body) — unchanged |
| #14 raw frontmatter required fields | file-based (raw out of scope) — unchanged |
| #15 raw immutability | file/git — unchanged |
| NEW | orphan-file / missing-body / path-drift (§6.1) |

### 6.3 Skill contract blast radius
Three SKILL.md files change:
- `wiki-authoring` — biggest: "copy template, fill frontmatter+body" → "write body, call `kb-page create`".
- `memory-report` — inlines wiki schemas per period; its "write summary" steps become `kb-page` calls.
- `wiki-approval` — least: `promote/approve/reject` keep their interface, route writes through the shared core.
Transition risk: a skill that still hand-writes a `.md` produces an orphan file → caught loudly by §6.1 and repaired by `kb-page import --all`. Run `import --all` as a safety net until all three are migrated.

## 7. Migration / initial import (`kb-page import --all`)

Idempotent and re-runnable (doubles as the §4.2 repair path).
- **Dry-run gate** (`--dry-run`): report would-be upserts, parse failures, stem/path collisions, and any page whose re-rendered frontmatter is not **semantically equal** to the original (zero-loss bar). 
- **Order:** parse all → validate roundtrip → **single transaction** of all `INSERT … ON CONFLICT(stem) DO UPDATE` upserts → commit → **then** render files. If file rendering dies mid-way, the DB is complete and canonical; re-running `render --all` (idempotent) finishes the files. No mixed DB/file state.
- **Verification:** re-run full `kb-lint-wiki`; `git diff` shows only frontmatter-block normalization, never body changes.
- **Rollback (two lines):** `git checkout data/wiki` (files) + drop/recreate the four new tables (DB).

## 8. API changes (review console)

- `GET /api/decisions`, `/api/queue`: frontmatter from SQL (fast), body from file when needed. Removes the on-demand directory-scan + YAML parse (the R1 read path Phase-2 deferred optimizing).
- `GET /api/pages/{stem}` — define DB/disk disagreement:
  - row + body present → 200 normal.
  - row + body missing → **200** with frontmatter + `body: null`, `body_missing: true`; lint ERRORs it (§6.1).
  - body present + no row → **404** (page isn't "real" yet); lint ERRORs the orphan file.
  - `rel_path` ≠ on-disk location → resolve by `stem` scan; serve it but lint ERRORs path drift.
- `PATCH` → shared core (§4): DB write + `wiki_edits` audit + file re-render (replaces the markdown-rewrite path).

## 9. Out of scope (v1)
- Body in DB (Option 2 full) — body stays file-SOT, explicitly not planned.
- `links` edge table and `raw_files` mirror — documented future targets (§2.7).
- **Multi-device sync caveat:** the pre-commit hook guarantees committed-files==DB only on the committing machine. Since `data/` is git-synced across devices, a render+commit on machine A produces files machine B's DB doesn't know about until B runs `kb-page import`/`render`. Acceptable for a single sequential operator; named here, not engineered around.

## 10. Implementation order (PR boundaries for writing-plans)

Each PR leaves the system working and is independently revertable.
- **PR 1 — schema + migration + shared write core (inert).** Alembic for `pages`/`page_tags`/`page_sources`/`page_aliases` + `wiki_edits.field` widening; `apply_frontmatter_change` core; `kb-page import --all` (idempotent) + `kb-page render`. DB populated, files normalized, nothing reads from DB yet. Reversible via §7 rollback.
- **PR 2 — CLI authoring verbs + lint split.** `kb-page create/set` (incl. move-on-retype); lint re-bucket (#5/#10/#11/#12) + the §6.1 reconciliation checks. Lint now validates DB.
- **PR 3 — API read-path + console PATCH cutover.** Switch `decisions.py`/`pages.py`/`queue` reads to SQL-frontmatter + file-body; point PATCH at the shared core; wire §8 disagreement handling. FE-touching → load `impeccable`.
- **PR 4 — skills + pre-commit hook.** Rewrite the three SKILL.md authoring contracts; add the `render --all` + lint hook.

## Appendix A — round-1 review fixes applied
DB Optimizer: dropped `rejected` from enum + `pages`=`data/wiki/`-only (B1); type↔review_status CHECK (B2); promoted `subtype`/`period_start`/`period_end`, fixed summary `extra` (B3); excluded `index` type (B4); added `page_aliases` v1 (B5); loose datetime CHECK (R2); `UNIQUE(rel_path)` (R3); four `pages` indexes + child-side join indexes (R4/R5); `json_valid` CHECK, no `extra` expression indexes (R6); ORM export (N1); `wiki_edits.field` widening (N2); retype transaction (N3).
Backend Architect: cut block-drift check → reconciliation checks (B1); single shared write core (B2); idempotent upsert + txn-then-render + repair + rollback (B3); API disagreement behavior (B4); #10 orphan re-bucketed hybrid + #5 retired sub-checks named (N1/N2); move-on-retype folded into `set` (N3); approve/reject/promote stay in `kb-wiki-review` via shared core (N5); pre-commit hook caveat under §9 (N6); in-YAML marker (N7); DB checks report `rel_path` (N8); PR boundaries (§10).
