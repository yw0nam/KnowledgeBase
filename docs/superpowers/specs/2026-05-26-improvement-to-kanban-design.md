# Improvement → Kanban Dispatch — Design Spec

**Date**: 2026-05-26
**Status**: Approved (brainstorming complete, ready for implementation plan)
**Implementation note**: Backend (BE) and Frontend (FE) sections are deliberately self-contained so they can be implemented in separate sessions. The API Contract (§7) is the only shared dependency.

## 1. Synopsis

- **Purpose**: Let the user dispatch an improvement page to a Hermes kanban board from the existing review console, without disturbing the current approve/reject lifecycle.
- **I/O**: User clicks "Send to Kanban" in console → backend creates Hermes kanban card and records the dispatch on the improvement page frontmatter.

## 2. Background

The KB cron pipeline already surfaces actionable items as `wiki/improvements/` pages: `kb-memory-daily` (03:30) creates them with `review_status: not_processed`, `kb-wiki-promote` (04:00) promotes worthy ones to `pending_for_approve`, and `kb-cron-wrapup` (05:00) extracts open improvements into the morning Slack digest's Action Items table.

Today the only user action on a page is `approve` / `reject`, both of which are semantically "is this durable knowledge?" There is no first-class action for "I direct you to act on this", and the user is left to manually copy the item into a separate tracker. The action item also has no shared identity across days — there is no record of which items have been picked up.

Hermes already ships a SQLite-backed kanban at `~/.hermes/kanban.db` (cited in `docs/db_informations/hermes-schema-reference.md:18`). Verified via `hermes kanban --help` during spec drafting: it provides per-board task management, comments, a dispatcher, and the `hermes kanban archive` rollback path used by this spec. A web dashboard subcommand (`hermes dashboard`, default port 9119, observed in `hermes --help`) is mentioned only to explain how a user could browse the board remotely; the spec does not depend on it.

## 3. Scope

**In scope (Phase 1):**
- Backend endpoint to list Hermes kanban boards.
- Backend endpoint to dispatch a `pending_for_approve` improvement page to a chosen board.
- Frontmatter additions on the improvement page that record every dispatch.
- Frontend "Send to Kanban" affordance on `DecisionDock`, independent of approve/reject.

**Out of scope (deferred to later phases):**
- Dispatching pages with `review_status` ∈ {`not_processed`, `approved`, `rejected`}. Approved-page dispatch is a real future need but requires new browsing UI beyond the current queue (`src/kb_mcp/web/routes/queue.py:85`), so it stays out of Phase 1.
- Auto-dispatch (Phase 1 is always user-initiated).
- Worker profiles (`claude-worker`, `opencode-worker`) and execution loop.
- Card status → page status sync.
- Tracking prose-only action items that have no backing improvement page.
- Auto-creating boards from KB. Boards must already exist in Hermes.
- Server-side idempotency tokens for retried dispatches (see §6.3.2 Retry semantics).

## 4. Success Criteria

1. From a `pending_for_approve` or `approved` improvement page in the console, the user can pick a board from a dropdown, optionally add a direction note, and click **Send to Kanban**.
2. After a successful dispatch, a card exists on the chosen Hermes board, and the page frontmatter has a new entry under `kanban_dispatches:`.
3. Failures are explicit, never silent. The success path writes both card and frontmatter. The failure paths are bounded: either nothing is written, or the response body explicitly names any orphan `task_id` the user must clean up (see §6.3.2 step 6). The system does not pretend success when only one side persisted.
4. The existing approve/reject flow is unchanged. All current tests pass without modification.
5. Re-dispatching the same page is allowed but the UI warns about previous dispatches.

## 5. Architecture Overview

```
┌────────────────────────────────────────────────────────────────────────┐
│  Review Console (React, frontend/)                                      │
│   - QueueRail / PageDetail (unchanged)                                  │
│   - DecisionDock (extended: + KanbanDispatchPanel)                      │
│        ├── board <select> fetched from GET /api/kanban/boards           │
│        ├── direction <textarea> (optional)                              │
│        └── "Send to Kanban" button → POST /api/pages/{stem}/send-to-... │
└────────────────────────────┬───────────────────────────────────────────┘
                             │ HTTP (loopback)
┌────────────────────────────▼───────────────────────────────────────────┐
│  FastAPI app (src/kb_mcp/web/)                                          │
│   - routes/queue.py, routes/pages.py (unchanged)                        │
│   - routes/kanban.py (NEW): boards list + send-to-kanban                │
│         calls hermes CLI as subprocess, parses JSON                     │
│         mutates wiki page frontmatter via existing _store helpers       │
└────────────────────────────┬───────────────────────────────────────────┘
                             │ subprocess
┌────────────────────────────▼───────────────────────────────────────────┐
│  Hermes kanban (~/.hermes/kanban.db, existing)                          │
│   - hermes kanban boards list --json                                    │
│   - hermes kanban create --board <slug> ... --json                      │
└────────────────────────────────────────────────────────────────────────┘
```

## 6. Backend (BE)

> **This section is self-contained.** A backend engineer can implement everything below using only §6, §7, and §10. They do not need to read the frontend section.

### 6.1 Data model change — improvement page frontmatter

Add an optional list field `kanban_dispatches` to the page frontmatter. The field is absent until the first dispatch.

```yaml
kanban_dispatches:
  - task_id: "t_a1b2c3d4"
    board: "kb-main"
    dispatched_at: "2026-05-26T10:23:00+09:00"
    direction: "Investigate Loki query labels for mcp_tool"
  - task_id: "t_e5f6g7h8"
    board: "kb-main"
    dispatched_at: "2026-05-27T09:11:00+09:00"
    direction: null
```

Rules:
- Order: append-only, newest at the end.
- `direction` is `null` if the user left the textarea empty.
- This field is **not** added to lint required-fields. Pages without it remain valid.
- `kb-lint-wiki` MUST be updated to recognise the field as an allowed optional key (no validation logic beyond accepting it).

### 6.2 New module — `src/kb_mcp/cli/wiki_review/_kanban.py`

Pure helpers used by the route layer. No FastAPI knowledge inside.

- `list_boards() -> list[Board]` — runs `hermes kanban boards list --json` [‡], parses, returns a list of dataclasses `Board(slug, name, counts)`. Raises `HermesUnavailable` on subprocess failure.
- `create_card(board_slug, title, body, metadata) -> Card` — runs `hermes kanban create --board <slug> --title ... --body ... --metadata <json> --json` [‡]. Returns `Card(task_id, board)`. Raises `HermesUnavailable` or `HermesRejected` (board missing, etc.).
- `append_dispatch(page_path, dispatch_entry) -> None` — loads frontmatter via existing `_store._split_frontmatter`, appends to `kanban_dispatches`, writes file back atomically (temp file + rename). Preserves body verbatim. Reuse the existing `add_frontmatter_lines` / `set_frontmatter_field` helpers in `_store.py` where they fit; otherwise add a list-append helper there rather than duplicating frontmatter logic in this module.

[‡] Flags marked with this dagger are not verified against the installed Hermes — see Appendix A items 1 and 2. The implementer must confirm flag names and JSON field shapes before relying on them. If a flag is missing, update §7 in lockstep with the substitute.

### 6.3 New module — `src/kb_mcp/web/routes/kanban.py`

```python
GET  /api/kanban/boards
POST /api/pages/{stem}/send-to-kanban
```

#### 6.3.1 `GET /api/kanban/boards`

- Response 200:
  ```json
  {
    "boards": [
      {"slug": "kb-main", "name": "KB Main", "counts": {"ready": 3, "todo": 0, "in_progress": 1, "blocked": 2, "done": 17}}
    ]
  }
  ```
- Response 503 (Hermes unavailable):
  ```json
  {"detail": "Hermes kanban is not reachable. Is the daemon running?"}
  ```
- Caching: in-memory 30s TTL on a module-level dict. Cache key is the constant string `"boards"`. Invalidated on successful POST below.

#### 6.3.2 `POST /api/pages/{stem}/send-to-kanban`

Request body (full optionality defined in §7.2):
```json
{
  "board_slug": "kb-main",
  "direction_note": "Investigate Loki query labels for mcp_tool"
}
```

Response 200:
```json
{
  "task_id": "t_a1b2c3d4",
  "board_slug": "kb-main",
  "dispatched_at": "2026-05-26T10:23:00+09:00"
}
```

Steps:
1. Resolve page path via `_store.resolve_stem(wiki_dir, stem)`. On `PageNotFound` → **404**. On `StemCollision` → **409** (multiple pages share the stem; pass an explicit relative path — surface the helper's message).
2. Require `review_status == "pending_for_approve"`. Reject with **409** otherwise. (Approved-page dispatch is deferred — see §9.)
3. Call `list_boards()` and verify `board_slug` exists. Reject with **400** if not.
4. Build the card body from the page title + page body + direction note (see §6.4).
5. Call `create_card(...)`. On `HermesUnavailable`, return **503**. On `HermesRejected`, return **502** with the upstream message.
6. Call `append_dispatch(page_path, …)`. If this raises, attempt rollback via `hermes kanban archive <task_id>` [†]. If rollback succeeds, return **500** with body `{"detail": "frontmatter write failed, kanban card rolled back"}`. If rollback also fails, return **500** with body `{"detail": "Card exists on board <slug> but the page frontmatter could not be updated. Archive it manually: hermes kanban archive <task_id>", "orphan_task_id": "<task_id>"}` — the extra `orphan_task_id` field is an exception to §7.2's `{detail}` shape and is the only place it appears.
7. Invalidate the boards cache.
8. Return success payload.

**Retry semantics:** This endpoint has **no idempotency key**. A client that retries after a network timeout (e.g. server completed step 6 but the response was lost) will create a second card. The UI's previous-dispatches list (§8.2) and re-dispatch warning (§8.3) are the user-visible mitigation; an idempotency token is deferred (out of scope for Phase 1 user-initiated flow).

[†] `archive` is verified to exist in `hermes kanban --help`. Whether it is the correct semantic for "undo a just-created card" is the implementer-verification item in Appendix A §3.

### 6.4 Card body composition

```
# {page_title}

Dispatched from KB review console.

Source page: {wiki/improvements/<YYYY-MM>/<stem>.md}

## Direction
{direction_note or "(none provided)"}

## Page contents
{verbatim body of the improvement page}
```

`metadata` JSON passed to `hermes kanban create`:
```json
{"kb_page_stem": "<stem>", "kb_source": "review-console"}
```

This metadata lets future tooling find which card came from which page without parsing the body.

### 6.5 Error class taxonomy

| Exception | HTTP | When |
|---|---|---|
| `HermesUnavailable` | 503 | subprocess timeout / CLI not found / daemon down |
| `HermesRejected(msg)` | 502 | non-zero exit with a parseable error |
| `PageNotFound` | 404 | stem lookup miss |
| `StemCollision` | 409 | multiple pages share the stem |
| `InvalidPageStatus` | 409 | review_status not `pending_for_approve` |
| `BoardNotFound` | 400 | board_slug not in current list |
| (rollback-failure body) | 500 | see §6.3.2 step 6 — body carries an extra `orphan_task_id` field |

### 6.6 Backend tests (required)

- Unit test for `_kanban.create_card` mocking subprocess: success path, non-zero exit, timeout.
- Unit test for `_kanban.append_dispatch`: appends to existing list; creates list if absent; preserves body and other frontmatter keys.
- Route test for `/api/kanban/boards`: success, cached second call, 503 on subprocess failure.
- Route test for `/api/pages/{stem}/send-to-kanban`: success (assert frontmatter mutated + response body), 404, 409, 400, 503, rollback path (frontmatter write fails, archive called).
- Lint test: a page with `kanban_dispatches` passes `kb-lint-wiki`.

### 6.7 Files touched (backend)

| File | Change |
|---|---|
| `src/kb_mcp/cli/wiki_review/_kanban.py` | NEW |
| `src/kb_mcp/web/routes/kanban.py` | NEW |
| `src/kb_mcp/web/app.py` | register new router |
| `src/kb_mcp/cli/lint_wiki.py` | allow optional `kanban_dispatches` key |
| `src/kb_mcp/cli/wiki_review/_store.py` | (only if needed) helper exports |
| `tests/web/test_kanban_route.py` | NEW |
| `tests/cli/test_kanban_helpers.py` | NEW |
| `CHANGELOG.md` | entry |

## 7. API Contract (FE ↔ BE)

This is the only section both implementers must agree on. **Do not change without updating both sides.**

### 7.1 GET /api/kanban/boards

- Method: `GET`
- Auth: none (loopback only, same as existing routes)
- Success 200 body:
  ```ts
  type BoardsResponse = {
    boards: Array<{
      slug: string;
      name: string;
      counts: { ready: number; todo: number; in_progress: number; blocked: number; done: number };
    }>;
  };
  ```
- Error body (all 4xx/5xx unless noted): `{ detail: string }`

### 7.2 POST /api/pages/{stem}/send-to-kanban

- Method: `POST`
- Path param: `stem` (filename without `.md`)
- Request body:
  ```ts
  type SendToKanbanRequest = {
    board_slug: string;
    direction_note?: string | null;
  };
  ```
- Success 200 body:
  ```ts
  type SendToKanbanResponse = {
    task_id: string;            // e.g. "t_a1b2c3d4"
    board_slug: string;
    dispatched_at: string;      // ISO-8601 with offset, KST
  };
  ```
- Error bodies: `{ detail: string }` for all 4xx/5xx codes listed in §6.5, **except** the rollback-failure 500 which additionally carries `orphan_task_id: string` (see §6.3.2 step 6). This is the single documented exception to the uniform error shape.

## 8. Frontend (FE)

> **This section is self-contained.** A frontend engineer can implement everything below using only §7 and §8. They do not need to read the backend section.

### 8.1 Component changes

- **New component**: `frontend/src/components/KanbanDispatchPanel.tsx` + `.module.css`
- **Edit**: `frontend/src/components/DecisionDock.tsx` — render `<KanbanDispatchPanel page={page} />` as a separate panel below the existing approve/reject controls. The two panels are visually distinct and operate independently.

### 8.2 `KanbanDispatchPanel` behaviour

State (local component):
- `boards: Board[] | null` — fetched on mount via `listKanbanBoards()`. `null` while loading.
- `selectedBoard: string | null` — initialised to the first board's slug once loaded.
- `directionNote: string` — controlled textarea, default `""`.
- `dispatching: boolean` — true while POST is in flight.
- `lastError: string | null` — error message from the most recent failed call.

Render order (top to bottom in the panel):
1. **Previous dispatches list** — rendered only if `page.frontmatter.kanban_dispatches` is non-empty. One line per entry: `dispatched_at` (formatted as `YYYY-MM-DD HH:mm KST`) + `task_id` + `board`. If the entry has a direction, render it underneath as muted text.
2. **Re-dispatch warning** (see §8.3) — only when the list above is non-empty.
3. **Board dropdown** — options labelled `${name} (${slug})`.
4. **Direction textarea** — placeholder "Direction (optional)".
5. **Send to Kanban button** — disabled while `dispatching` is true.
6. **Error line** — render `lastError` below the button in error styling.

Loading and empty states override the order above:
- While `boards === null`: render only a single-line placeholder "Loading kanban boards…".
- If `boards.length === 0`: render only "No kanban boards registered. Run `hermes kanban boards create <slug>` first." Do not render the button.

After a successful dispatch: show a toast (reuse existing toast infrastructure if present, else a transient inline banner) with text `Sent to ${board_slug} as ${task_id}`. Refresh the focused page so the new dispatch appears in the previous-dispatches list. Clear `lastError`.

On error: render `lastError` below the button. Do not clear it on next focus change; clear it only when the user changes any input or clicks the button again.

### 8.3 Re-dispatch UX

If `page.frontmatter.kanban_dispatches` already has at least one entry, the button label changes to **Send again to Kanban**, and a small warning is shown above the button: "This page has been dispatched N time(s). A new card will be created."

### 8.4 API client additions — `frontend/src/api.ts`

```ts
export async function listKanbanBoards(): Promise<BoardsResponse> { /* GET /api/kanban/boards */ }
export async function sendPageToKanban(stem: string, payload: SendToKanbanRequest): Promise<SendToKanbanResponse> { /* POST */ }
```

Both functions throw `ApiError` on non-2xx. The existing `ApiError` class (`frontend/src/api.ts:16`) carries `status: number` and `message: string`; the FastAPI `detail` is extracted from the response body and passed as `message` (matching the existing pattern at `frontend/src/api.ts:52-57`). For the rollback-failure 500, `message` is the `detail` text; the additional `orphan_task_id` field must be parsed from the response body separately — extend `ApiError` (or add a sibling helper) so this value reaches the panel.

### 8.5 Type definitions — `frontend/src/types.ts`

Add the request/response types from §7. Also extend the existing `PageFrontmatter` type with:
```ts
kanban_dispatches?: Array<{
  task_id: string;
  board: string;
  dispatched_at: string;
  direction?: string | null;
}>;
```

### 8.6 Frontend tests (required)

- Unit: panel renders loading → boards → list correctly.
- Unit: empty-boards path renders the install hint and disables the button.
- Unit: re-dispatch warning appears when `kanban_dispatches.length > 0`.
- Integration (with mocked fetch): success path triggers refresh; 503 renders error; 502 renders upstream error verbatim.

### 8.7 Files touched (frontend)

| File | Change |
|---|---|
| `frontend/src/components/KanbanDispatchPanel.tsx` | NEW |
| `frontend/src/components/KanbanDispatchPanel.module.css` | NEW |
| `frontend/src/components/DecisionDock.tsx` | embed panel |
| `frontend/src/api.ts` | two new fns |
| `frontend/src/types.ts` | new types + frontmatter extension |
| `frontend/src/components/__tests__/KanbanDispatchPanel.test.tsx` | NEW |

## 9. Out of Scope (Recap)

- Anything that touches `kb-memory-daily`, `kb-wiki-promote`, `kb-cron-wrapup`, or `morning-slack-digest`.
- Hermes board creation, Hermes worker profiles, automatic execution.
- Two-way sync between kanban card lifecycle and page lifecycle.
- Prose-only action items in the Slack digest that have no backing improvement page.

## 10. Implementation Order

Designed so BE and FE can proceed in parallel after the API contract (§7) is locked.

1. **Lock contract.** Both implementers read §7 and confirm. No code yet.
2. **BE-1**: `_kanban.py` helpers + tests. (Mock subprocess; no real Hermes needed.)
3. **BE-2**: `routes/kanban.py` + tests. App-level integration test using a fake helper.
4. **BE-3**: Lint update for `kanban_dispatches`. Run full lint suite on existing wiki.
5. **FE-1**: types + api.ts. No UI yet.
6. **FE-2**: `KanbanDispatchPanel` component + tests against mocked fetch.
7. **FE-3**: integrate into `DecisionDock`. Manual smoke against running backend.
8. **Joint smoke test**: dispatch a real `pending_for_approve` page to a real Hermes board. Verify card on `hermes dashboard` + frontmatter entry.
9. **CHANGELOG + commit** (outer repo only — `data/` not affected by this change set).

## 11. Risks

| Risk | Mitigation |
|---|---|
| Hermes CLI output format changes silently | Pin to the JSON output of `hermes kanban boards list --json` and `create --json`. Add a single integration test that asserts the field names we depend on; it fails fast on upgrades. |
| Half-state: card created, frontmatter write fails | Explicit rollback in §6.3.2 step 6. Last-resort error message includes the orphan task_id so the user can clean up. |
| User dispatches the same page repeatedly by accident | UI re-dispatch warning (§8.3). Backend does not dedup (it is a user-initiated action, not an automation). |
| Boards endpoint slow on every keystroke | 30s in-memory TTL (§6.3.1). Invalidated on successful dispatch. |

## Appendix A — Implementer verification items

Items already confirmed during spec drafting (do not re-verify):

- `hermes kanban` has `boards`, `create`, `comment`, `list`, `archive` subcommands (observed in `hermes kanban --help`).
- `hermes dashboard` exists with default port 9119 (observed in `hermes --help`).
- `~/.hermes/kanban.db` is the canonical SQLite path (cited in `docs/db_informations/hermes-schema-reference.md:18`).

Before writing code, the BE implementer must confirm the following against the installed Hermes version:

1. `hermes kanban boards list --json` exists and the field names used in §7.1 (`slug`, `name`, `counts.{ready,todo,in_progress,blocked,done}`) match the actual output. If field names differ, update §7.1 and the FE types in lockstep.
2. `hermes kanban create` accepts `--metadata <json>` and `--json` flags. If `--metadata` is unsupported, fall back to embedding the metadata pair as a trailing line in the card body and remove §6.4's metadata block from the contract.
3. `hermes kanban archive <task_id>` is semantically correct as a rollback for a card created seconds earlier (the command exists; only its effect on a fresh card needs confirmation — does the dispatcher leave it alone? does it disappear from the active queue?).

The KB implementer must confirm:

4. `kb-lint-wiki` does not currently reject unknown frontmatter keys, OR §6.1's lint update is needed. Check `src/kb_mcp/cli/lint_wiki.py` for an allowed-keys list before assuming the change is no-op.

## Appendix B — Patch notes

- 2026-05-26: initial draft.
- 2026-05-26 (rev1): Codex independent review. Fixes:
  - §4.3 success criterion no longer overpromises atomicity; replaced "no half-state" with "explicit failures, named orphan task_id".
  - §6.3.2 dispatch limited to `pending_for_approve` only; approved-page dispatch moved to §9 future scope (queue.py does not surface approved pages today).
  - §6.3.2 step 1 uses real helper name `resolve_stem` and routes `StemCollision` → 409.
  - §6.3.2 step 6 pins rollback-failure body shape to `{detail, orphan_task_id}`; §7.2 documents the one exception to the uniform error shape.
  - §6.3.2 adds explicit "Retry semantics" note — no idempotency token in Phase 1.
  - §7.2 / §8.4: error field is `message` (matches existing `ApiError`), not `detail`.
  - §6.3.2 JSON example no longer contains a `// optional` comment.
  - §6.2 marks unverified Hermes flags with [‡] linking to Appendix A.
  - Background (§2) trimmed to facts verified during drafting; Appendix A separates "already confirmed" from "must verify before coding".
