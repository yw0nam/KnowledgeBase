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
  // Response body still uses `board_slug` (spec §7.2 response model).
  // Do not confuse this with the persisted frontmatter entry, which
  // uses `board` (see KanbanDispatchRecord below).
  task_id: string;
  board_slug: string;
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
// this type just documents the kanban_dispatches subfield.
export interface PageFrontmatter extends Frontmatter {
  kanban_dispatches?: KanbanDispatchRecord[];
}
