// Mirrors the response shape from /api/queue (see
// src/kb_mcp/web/routes/queue.py). Frontmatter is a free dict because
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
