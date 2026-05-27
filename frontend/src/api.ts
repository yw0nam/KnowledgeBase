// Typed fetch wrapper + frontmatter accessors. Single source of
// truth for talking to the FastAPI backend. No retries, no caching —
// the API is local and the network round-trip is sub-millisecond.

import type {
  BoardsResponse,
  CategoryEnumsResponse,
  DecisionsResponse,
  DispatchesResponse,
  Frontmatter,
  FrontmatterPatch,
  FrontmatterPatchResponse,
  QueueResponse,
  ReviewPage,
  SendToKanbanRequest,
  SendToKanbanResponse,
  TimelineResponse,
  WikiEditsResponse,
  WikiType,
} from './types';

const WIKI_TYPES: ReadonlySet<WikiType> = new Set<WikiType>([
  'entity',
  'concept',
  'decision',
  'improvement',
  'checklist',
  'question',
]);

export class ApiError extends Error {
  status: number;
  // Populated when the rollback path failed and Hermes left a task
  // behind that the user must reclaim. See send-to-kanban 500 body
  // shape `{detail, orphan_task_id}`.
  orphan_task_id?: string;
  // Populated when PATCH /api/pages/{stem}/frontmatter returns 409
  // because the candidate failed kb-lint-wiki. Spec §6.4 body is
  // `{detail, lint_errors: [...]}`.
  lint_errors?: string[];
  constructor(
    status: number,
    message: string,
    extras?: { orphan_task_id?: string; lint_errors?: string[] },
  ) {
    super(message);
    this.status = status;
    this.name = 'ApiError';
    if (extras?.orphan_task_id) this.orphan_task_id = extras.orphan_task_id;
    if (extras?.lint_errors) this.lint_errors = extras.lint_errors;
  }
}

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(path, { headers: { Accept: 'application/json' } });
  if (!res.ok) {
    throw new ApiError(res.status, `${res.status} ${res.statusText} on ${path}`);
  }
  return (await res.json()) as T;
}

export function fetchQueue(): Promise<QueueResponse> {
  return getJson<QueueResponse>('/api/queue');
}

// GET /api/pages/{stem} — full page with body. Used by the Decisions
// browser to render markdown in the center panel without dragging in
// the whole queue payload. 404 means the page is no longer on disk
// (commonly: rejected and moved to data/rejected/).
export function fetchPageWithBody(stem: string): Promise<ReviewPage> {
  return getJson<ReviewPage>(`/api/pages/${encodeURIComponent(stem)}`);
}

interface DecisionResponse {
  stem: string;
  status: 'approved' | 'rejected';
}

async function postDecision(path: string, feedback: string): Promise<DecisionResponse> {
  const res = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify({ feedback }),
  });
  if (!res.ok) {
    // FastAPI returns { detail: "..." } on HTTPException.
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = (await res.json()) as { detail?: string };
      if (body?.detail) detail = body.detail;
    } catch {
      // body wasn't json; keep the status-line detail.
    }
    throw new ApiError(res.status, detail);
  }
  return (await res.json()) as DecisionResponse;
}

export function approvePage(stem: string, feedback: string): Promise<DecisionResponse> {
  return postDecision(`/api/pages/${encodeURIComponent(stem)}/approve`, feedback);
}

export function rejectPage(stem: string, feedback: string): Promise<DecisionResponse> {
  return postDecision(`/api/pages/${encodeURIComponent(stem)}/reject`, feedback);
}

// ── Kanban dispatch endpoints. ───────────────────────────────────

export function listKanbanBoards(): Promise<BoardsResponse> {
  return getJson<BoardsResponse>('/api/kanban/boards');
}

export async function sendPageToKanban(
  stem: string,
  payload: SendToKanbanRequest,
): Promise<SendToKanbanResponse> {
  const res = await fetch(`/api/pages/${encodeURIComponent(stem)}/send-to-kanban`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    // FastAPI returns `{detail: ...}` on HTTPException. The rollback
    // failure path also includes `{orphan_task_id}` which we surface
    // verbatim so the UI can render the reclaim instruction.
    let detail = `${res.status} ${res.statusText}`;
    let orphan: string | undefined;
    try {
      const body = (await res.json()) as {
        detail?: string;
        orphan_task_id?: string;
      };
      if (body?.detail) detail = body.detail;
      if (typeof body?.orphan_task_id === 'string') orphan = body.orphan_task_id;
    } catch {
      // body wasn't json; keep the status-line detail.
    }
    throw new ApiError(res.status, detail, { orphan_task_id: orphan });
  }
  return (await res.json()) as SendToKanbanResponse;
}

// ── Phase 2: decisions, frontmatter PATCH, audit + enums. ─────────

function buildQuery(params: Record<string, unknown>): string {
  const usp = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === '') continue;
    if (Array.isArray(value)) {
      for (const v of value) {
        if (v === undefined || v === null || v === '') continue;
        usp.append(key, String(v));
      }
    } else {
      usp.append(key, String(value));
    }
  }
  const q = usp.toString();
  return q ? `?${q}` : '';
}

export interface DecisionsQuery {
  // Each filter is multi-valued, mirroring the BE Query(default=None)
  // list bindings in src/kb/web/routes/decisions.py.
  status?: string[];
  type?: string[];
  category?: string[];
  source?: string[];
  edited_since?: string;
  // Server-side filter for the "Dispatched" sub-tab. true → only
  // pages with a non-null dispatch_summary; false → only pages
  // without; absent = no filter.
  has_dispatch?: boolean;
  page?: number;
  per_page?: number;
}

export function fetchDecisions(q: DecisionsQuery = {}): Promise<DecisionsResponse> {
  return getJson<DecisionsResponse>(`/api/decisions${buildQuery({ ...q })}`);
}

export function fetchEdits(
  stem: string,
  q: { since?: string; limit?: number } = {},
): Promise<WikiEditsResponse> {
  return getJson<WikiEditsResponse>(
    `/api/pages/${encodeURIComponent(stem)}/edits${buildQuery(q)}`,
  );
}

export function fetchTimeline(
  stem: string,
  q: { since?: string; limit?: number } = {},
): Promise<TimelineResponse> {
  return getJson<TimelineResponse>(
    `/api/pages/${encodeURIComponent(stem)}/timeline${buildQuery(q)}`,
  );
}

export function fetchCategoryEnums(type?: string): Promise<CategoryEnumsResponse> {
  return getJson<CategoryEnumsResponse>(`/api/enums/categories${buildQuery({ type })}`);
}

export async function patchFrontmatter(
  stem: string,
  patch: FrontmatterPatch,
): Promise<FrontmatterPatchResponse> {
  const res = await fetch(`/api/pages/${encodeURIComponent(stem)}/frontmatter`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify(patch),
  });
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    let lintErrors: string[] | undefined;
    try {
      const body = (await res.json()) as {
        detail?: string;
        lint_errors?: unknown;
      };
      if (body?.detail) detail = body.detail;
      if (Array.isArray(body?.lint_errors)) {
        lintErrors = body.lint_errors.filter((x): x is string => typeof x === 'string');
      }
    } catch {
      // fall through with status-line detail
    }
    throw new ApiError(res.status, detail, { lint_errors: lintErrors });
  }
  return (await res.json()) as FrontmatterPatchResponse;
}

// ── Dispatch ledger (read + status push + cancel). ────────────────

export interface DispatchesQuery {
  page_stem?: string;
  status?: string[];
  since?: string;
  limit?: number;
}

export function listDispatches(q: DispatchesQuery = {}): Promise<DispatchesResponse> {
  return getJson<DispatchesResponse>(`/api/dispatches${buildQuery({ ...q })}`);
}

export interface DispatchStatusBody {
  status: 'in_progress' | 'done' | 'failed' | 'cancelled';
  result_payload?: Record<string, unknown> | null;
  occurred_at?: string;
}

export async function postDispatchStatus(
  id: number,
  body: DispatchStatusBody,
  token: string,
): Promise<unknown> {
  const res = await fetch(`/api/dispatches/${id}/status`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const j = (await res.json()) as { detail?: string };
      if (j?.detail) detail = j.detail;
    } catch {
      // keep status-line detail
    }
    throw new ApiError(res.status, detail);
  }
  return res.json();
}

export interface DispatchCancelError {
  detail: string;
  db_state?: string;
  external_error?: string;
}

export async function postDispatchCancel(
  id: number,
  opts: { force?: boolean } = {},
): Promise<unknown> {
  const q = buildQuery({ force: opts.force ? 'true' : undefined });
  const res = await fetch(`/api/dispatches/${id}/cancel${q}`, {
    method: 'POST',
    headers: { Accept: 'application/json' },
  });
  if (!res.ok) {
    let detail: DispatchCancelError = {
      detail: `${res.status} ${res.statusText}`,
    };
    try {
      const j = (await res.json()) as DispatchCancelError;
      if (j?.detail) detail = j;
    } catch {
      // keep default
    }
    throw new ApiError(res.status, detail.detail);
  }
  return res.json();
}

// ── Frontmatter accessors. ────────────────────────────────────
// These keep the rest of the app from knowing how frontmatter is
// structured. Unknown values fall back to honest empty/undefined,
// never fabricated.

export function fmString(fm: Frontmatter, key: string): string | undefined {
  const v = fm[key];
  return typeof v === 'string' ? v : undefined;
}

export function fmList(fm: Frontmatter, key: string): string[] {
  const v = fm[key];
  if (Array.isArray(v)) {
    return v.filter((x): x is string => typeof x === 'string');
  }
  return [];
}

export function pageTitle(page: ReviewPage): string {
  const fmTitle = fmString(page.frontmatter, 'title');
  if (fmTitle) return fmTitle;
  // Fallback: first H1 in body.
  const h1 = page.body.match(/^#\s+(.+)$/m);
  if (h1?.[1]) return h1[1].trim();
  return page.stem;
}

export function pageType(page: ReviewPage): WikiType | undefined {
  const t = fmString(page.frontmatter, 'type');
  return t && WIKI_TYPES.has(t as WikiType) ? (t as WikiType) : undefined;
}

export function pageSources(page: ReviewPage): string[] {
  return fmList(page.frontmatter, 'sources');
}

export function pageCreated(page: ReviewPage): string | undefined {
  return (
    fmString(page.frontmatter, 'created') ?? fmString(page.frontmatter, 'captured_at')
  );
}

export function ageLabel(iso: string | undefined, now: Date = new Date()): string {
  if (!iso) return '—';
  const then = new Date(iso);
  if (Number.isNaN(then.getTime())) return '—';
  const seconds = Math.max(0, (now.getTime() - then.getTime()) / 1000);
  if (seconds < 60) return 'now';
  const minutes = seconds / 60;
  if (minutes < 60) return `${Math.round(minutes)}m`;
  const hours = minutes / 60;
  if (hours < 24) return `${Math.round(hours)}h`;
  const days = hours / 24;
  if (days < 30) return `${Math.round(days)}d`;
  const months = days / 30;
  if (months < 12) return `${Math.round(months)}mo`;
  return `${Math.round(months / 12)}y`;
}
