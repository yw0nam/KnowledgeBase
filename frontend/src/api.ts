// Typed fetch wrapper + frontmatter accessors. Single source of
// truth for talking to the FastAPI backend. No retries, no caching —
// the API is local and the network round-trip is sub-millisecond.

import type { Frontmatter, QueueResponse, ReviewPage, WikiType } from './types';

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
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = 'ApiError';
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
