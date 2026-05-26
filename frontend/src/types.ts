// Mirrors the response shape from /api/queue (see
// src/kb/web/routes/queue.py). Frontmatter is a free dict because
// wiki frontmatter is open-ended; known fields are accessed via
// helpers in api.ts.

export type Frontmatter = Record<string, unknown>;

export interface ReviewPage {
  stem: string;
  rel_path: string;
  abs_path: string;
  frontmatter: Frontmatter;
  body: string;
}

export interface QueueMeta {
  data_dir: string;
  wiki_dir: string;
  wiki_exists: boolean;
  count: number;
  git_indexed: boolean;
}

export interface QueueResponse {
  pages: ReviewPage[];
  meta: QueueMeta;
}

export type WikiType =
  | 'entity'
  | 'concept'
  | 'decision'
  | 'improvement'
  | 'checklist'
  | 'question';

// ── Kanban dispatch (improvement → Hermes kanban). ───────────────
// /api/kanban/boards returns a sparse counts map: only non-zero
// status buckets appear, and the dict may be empty. Do not assume
// fixed keys like {ready, todo, in_progress, blocked, done}.
export interface Board {
  slug: string;
  name: string;
  counts: Record<string, number>;
}

export interface BoardsResponse {
  boards: Board[];
}

export interface SendToKanbanRequest {
  board_slug: string;
  // Spec §7.2: request body field is `direction_note`, nullable. BE
  // is Pydantic v2 and silently drops unknown keys, so a name drift
  // here makes every dispatch persist with no direction.
  direction_note?: string | null;
}

export interface SendToKanbanResponse {
  // Phase 2 (spec §6.2): dispatch is persisted to the operational DB,
  // not frontmatter. Response carries the row's id and the same
  // task/board IDs under generic names.
  id: number;
  external_task_id: string;
  external_board_id: string;
  dispatched_at: string;
}

// One dispatch record persisted on the improvement page's frontmatter
// after a successful POST /api/pages/{stem}/send-to-kanban. Spec §6.1
// example writes `board:` (not `board_slug:`).
export interface KanbanDispatchRecord {
  board: string;
  task_id: string;
  dispatched_at: string;
  direction?: string;
}

// Optional shape we read off Frontmatter when present. The page's
// frontmatter is still typed broadly as Frontmatter (an open dict);
// this type just documents the kanban_dispatches subfield. Phase 2
// removed this field from new pages; the type stays here only so the
// migration smoke-test page (pre-backfill) still parses cleanly.
export interface PageFrontmatter extends Frontmatter {
  kanban_dispatches?: KanbanDispatchRecord[];
}

// ── Phase 2 decision browser. ─────────────────────────────────────

// One row in GET /api/decisions (see src/kb/web/routes/decisions.py).
// `category` is an open string per spec §6.4 — never a typed enum.
export interface Decision {
  stem: string;
  path: string;
  type: string | null;
  category: string | null;
  tags: string[];
  review_status: string | null;
  sources: string[];
  captured_at: string | null;
  last_edited_at: string | null;
  dispatch_summary: { count: number; last_status: string } | null;
}

export interface DecisionsResponse {
  items: Decision[];
  total: number;
  page: number;
  per_page: number;
}

// PATCH /api/pages/{stem}/frontmatter merge patch body. Absent =
// unchanged, [] for tags = clear all tags. `type` is constrained;
// `category` is open string; `tags` is a full replacement.
export interface FrontmatterPatch {
  review_status?: 'pending_for_approve' | 'approved' | 'rejected' | 'not_processed';
  type?:
    | 'entity'
    | 'concept'
    | 'decision'
    | 'question'
    | 'improvement'
    | 'checklist'
    | 'summary';
  category?: string | null;
  tags?: string[];
}

export interface FrontmatterPatchResponse {
  stem: string;
  frontmatter: Frontmatter;
  edits: { field: string; edited_at: string }[];
}

// 409 body when lint fails inside PATCH (spec §6.4). FE renders the
// linter's errors inline under the offending field.
export interface FrontmatterPatchLintError {
  detail: string;
  lint_errors: string[];
}

// GET /api/pages/{stem}/edits row (audit log, append-only).
export interface WikiEdit {
  id: number;
  page_stem: string;
  field: string;
  old_value: unknown;
  new_value: unknown;
  edited_at: string;
  source: string;
}

export interface WikiEditsResponse {
  items: WikiEdit[];
  total: number;
}

// GET /api/pages/{stem}/timeline event. Discriminated by `kind`:
//   - 'edit'           : wiki_edits row.
//   - 'dispatched'     : the moment a dispatch was created.
//   - 'status:<status>': last status push for a dispatch (no per-
//                        transition history; see spec §6.4).
export type TimelineEvent =
  | {
      kind: 'edit';
      at: string;
      field: string;
      old_value: unknown;
      new_value: unknown;
      source: string;
    }
  | {
      kind: 'dispatched';
      at: string;
      dispatch_id: number;
      external_task_id: string;
    }
  | {
      // `kind` is literally `status:<status>` (e.g. `status:done`).
      kind: string;
      at: string;
      dispatch_id: number;
      external_task_id: string;
    };

export interface TimelineResponse {
  items: TimelineEvent[];
  total: number;
}

// GET /api/dispatches row payload. Matches src/kb/web/routes/dispatches.py
// `_row_payload` exactly.
export interface DispatchRecord {
  id: number;
  page_stem: string;
  page_path_at_dispatch: string;
  external_board_id: string;
  external_task_id: string;
  direction: string | null;
  status: string;
  idempotency_key: string | null;
  created_at: string;
  dispatched_at: string;
  last_status_at: string | null;
  result_payload: unknown;
}

export interface DispatchesResponse {
  items: DispatchRecord[];
  total: number;
}

// GET /api/enums/categories — open string list, may be empty.
export interface CategoryEnumsResponse {
  categories: string[];
}
