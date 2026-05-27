// Coverage for the markdown body panel added to DecisionsPage:
//   1. empty-state placeholder when no stem selected (no list rows)
//   2. "Loading body…" → PageDetail body when fetch resolves
//   3. friendly "Page not found" copy when /api/pages/{stem} → 404

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { DecisionsPage } from '../DecisionsPage';

interface MockResponseInit {
  status?: number;
  body?: unknown;
}

function mockResponse({ status = 200, body = {} }: MockResponseInit): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: status === 200 ? 'OK' : 'NOT FOUND',
    json: async () => body,
  } as unknown as Response;
}

function decisionsResponse(items: unknown[] = []) {
  return {
    items,
    total: items.length,
    page: 1,
    per_page: 50,
  };
}

function makeDecisionRow(stem: string) {
  return {
    stem,
    path: `wiki/decisions/${stem}.md`,
    type: 'decision',
    category: 'system-ops',
    tags: [],
    review_status: 'approved',
    sources: ['raw/manual/2026-05-27-seed.md'],
    captured_at: '2026-05-01T12:00:00+09:00',
    last_edited_at: '2026-05-26T14:23:00+09:00',
    dispatch_summary: null,
  };
}

function pageResponse(stem: string, body: string) {
  return {
    stem,
    rel_path: `decisions/${stem}.md`,
    abs_path: `/tmp/data/wiki/decisions/${stem}.md`,
    frontmatter: {
      title: stem,
      type: 'decision',
      review_status: 'approved',
      sources: ['raw/manual/seed.md'],
    },
    body,
  };
}

const fetchMock = vi.fn();

beforeEach(() => {
  fetchMock.mockReset();
  globalThis.fetch = fetchMock as unknown as typeof fetch;
});

afterEach(() => {
  vi.useRealTimers();
});

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <DecisionsPage />
    </MemoryRouter>,
  );
}

describe('DecisionsPage body panel', () => {
  it('shows the empty-state placeholder when no row is selected', async () => {
    // No items in the list → no auto-select → no body fetch. The
    // center panel must show the calm operator copy, not a blank.
    fetchMock.mockImplementation((url: string) => {
      if (url.startsWith('/api/decisions'))
        return Promise.resolve(mockResponse({ body: decisionsResponse([]) }));
      if (url.startsWith('/api/enums/categories'))
        return Promise.resolve(mockResponse({ body: { categories: [] } }));
      return Promise.resolve(mockResponse({ status: 404, body: { detail: 'nope' } }));
    });

    renderAt('/decisions?tab=approved');

    await waitFor(() => {
      expect(
        screen.getByText(/select a page from the list to read its content/i),
      ).toBeInTheDocument();
    });
    // No body fetch should have been attempted with an empty list.
    const bodyCalls = fetchMock.mock.calls.filter(([url]) =>
      /^\/api\/pages\/[^/]+$/.test(String(url)),
    );
    expect(bodyCalls).toHaveLength(0);
  });

  it('renders "Loading body…" then the rendered markdown when the fetch resolves', async () => {
    const row = makeDecisionRow('decide-thing');
    // Deferred via an external resolver so the test can assert on the
    // "Loading body…" line before the body lands.
    let resolvePage!: (res: Response) => void;
    const pagePromise = new Promise<Response>((resolve) => {
      resolvePage = resolve;
    });

    fetchMock.mockImplementation((url: string) => {
      if (url.startsWith('/api/decisions'))
        return Promise.resolve(mockResponse({ body: decisionsResponse([row]) }));
      if (url.startsWith('/api/enums/categories'))
        return Promise.resolve(mockResponse({ body: { categories: [] } }));
      if (url === `/api/pages/${row.stem}`) return pagePromise;
      if (url.includes('/timeline'))
        return Promise.resolve(mockResponse({ body: { items: [], total: 0 } }));
      return Promise.resolve(mockResponse({ body: {} }));
    });

    renderAt('/decisions?tab=approved');

    // Auto-select kicks in: list renders the row, then the body fetch
    // is in-flight. Loading line must show before resolution.
    await waitFor(() => {
      expect(screen.getByText(/loading body/i)).toBeInTheDocument();
    });

    // Resolve the body fetch with a tiny markdown payload.
    resolvePage(
      mockResponse({
        body: pageResponse(
          row.stem,
          '## A heading\n\nA paragraph with **bold** text.\n',
        ),
      }),
    );

    // PageDetail renders the rel_path mono line and the markdown body.
    await waitFor(() => {
      expect(screen.getByText(`decisions/${row.stem}.md`)).toBeInTheDocument();
    });
    expect(screen.getByRole('heading', { name: /a heading/i })).toBeInTheDocument();
    expect(screen.getByText(/bold/i)).toBeInTheDocument();
    // Loading line is gone.
    expect(screen.queryByText(/^loading body…$/i)).not.toBeInTheDocument();
  });

  it('shows the not-found copy when GET /api/pages/{stem} returns 404', async () => {
    const row = makeDecisionRow('ghost-page');
    fetchMock.mockImplementation((url: string) => {
      if (url.startsWith('/api/decisions'))
        return Promise.resolve(mockResponse({ body: decisionsResponse([row]) }));
      if (url.startsWith('/api/enums/categories'))
        return Promise.resolve(mockResponse({ body: { categories: [] } }));
      if (url === `/api/pages/${row.stem}`)
        return Promise.resolve(
          mockResponse({ status: 404, body: { detail: 'no page with stem' } }),
        );
      if (url.includes('/timeline'))
        return Promise.resolve(mockResponse({ body: { items: [], total: 0 } }));
      return Promise.resolve(mockResponse({ body: {} }));
    });

    renderAt('/decisions?tab=approved');

    await waitFor(() => {
      const notFound = screen.getByText(/page not found on disk/i);
      expect(notFound).toBeInTheDocument();
      // The same paragraph names the rejected/ destination so the
      // operator knows where to look. Assert on the parent's textContent
      // since /rejected/i alone is ambiguous (the inspector shows a
      // `review_status` chip elsewhere on the page).
      expect(notFound.textContent ?? '').toMatch(/rejected\//i);
    });
  });
});
